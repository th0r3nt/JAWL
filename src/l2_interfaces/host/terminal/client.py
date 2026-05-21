"""
Local TCP server of the terminal (user CLI interface).

Provides bi-directional communication between the command line interface (UI)
and the agent's EventBus. Protected by a Handshake mechanism that
ignores OS and IDE port scanners (which like to knock on all open sockets).
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import main_logger
from src.utils.dtime import get_now_formatted
from src.utils.settings import HostTerminalConfig
from src.l2_interfaces.host.terminal.state import HostTerminalState


class HostTerminalClient:
    """
    Local terminal TCP server.
    Manages CLI chat connections and message delivery.
    """

    def __init__(
        self,
        state: HostTerminalState,
        config: HostTerminalConfig,
        data_dir: Path,
        agent_name: str,
        timezone: int,
    ) -> None:
        """
        Initializes the terminal TCP server.

        Args:
            state: Terminal L0 state.
            config: Configuration.
            data_dir: JAWL local data root directory.
            agent_name: Agent name to display in the UI.
            timezone: Timezone offset.
        """
        self.state = state
        self.config = config
        self.agent_name = agent_name
        self.timezone = timezone

        self.host = "127.0.0.1"
        self.port = 0  # 0 means the OS will issue any free port automatically

        # Interface state files
        self.history_file = data_dir / "interfaces" / "host" / "terminal" / "history.json"
        self.port_file = (
            data_dir / "interfaces" / "host" / "terminal" / "terminal.port"
        )  # Port file

        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        self.server: Optional[asyncio.AbstractServer] = None
        self.active_writers: set[asyncio.StreamWriter] = set()

        # Queue to pass incoming messages/signals to events.py
        # Format: (action_type, payload)
        self.incoming_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    async def start(self) -> None:
        """Starts the TCP server and saves the OS-issued port to a file for the UI."""
        self._load_history()

        # OS will issue a free port on its own
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)

        # Retrieve the actual issued port number
        actual_port = self.server.sockets[0].getsockname()[1]

        # Save it to a file so that the CLI knows where to connect
        self.port_file.write_text(str(actual_port))
        self.state.is_online = True

        main_logger.info(f"[Host OS] Terminal server started ({self.host}:{actual_port})")

    async def stop(self) -> None:
        """Correctly closes all active sockets."""
        self.state.is_online = False

        # Delete port file since it is no longer needed
        if self.port_file.exists():
            try:
                self.port_file.unlink()
            except Exception:
                pass

        for writer in list(self.active_writers):
            writer.close()
            await writer.wait_closed()

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        main_logger.info("[Host OS] Terminal server stopped.")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """
        Coroutine of handling new TCP connection.
        Awaits 'JAWL_HANDSHAKE' password (spam protection) and transmits
        incoming text streams into the queue for processing by the Events module.
        """

        try:
            # Wait for the handshake password for a maximum of 2 seconds
            handshake = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if handshake.decode("utf-8").strip() != "JAWL_HANDSHAKE":
                writer.close()
                await writer.wait_closed()
                return
        except (asyncio.TimeoutError, Exception):
            # If a port scanner connected and remains silent - drop it
            writer.close()
            return

        # If password is correct - let it in
        self.active_writers.add(writer)

        if not self.state.is_ui_connected:
            self.state.is_ui_connected = True
            main_logger.info("[Host OS] CLI chat connected to the terminal.")
            await self.incoming_queue.put(("_CONNECTION_OPENED", ""))

        try:
            while True:
                data = await reader.readline()
                if not data:
                    break  # Disconnected

                text = data.decode("utf-8").strip()
                if text:
                    # Extract JSON payload
                    try:
                        parsed = json.loads(text)
                        msg_text = parsed.get("text", text)
                    except json.JSONDecodeError:
                        msg_text = text

                    if msg_text:
                        time_str = get_now_formatted(self.timezone, "%Y-%m-%d %H:%M:%S")
                        self._record_message("User", msg_text, time_str)
                        await self.incoming_queue.put(("_MESSAGE", msg_text))

        except asyncio.CancelledError:
            pass

        except Exception as e:
            main_logger.warning(f"[Host OS] Terminal connection error: {e}")

        finally:
            self.active_writers.discard(writer)

            # Check if there are any active sessions left
            if not self.active_writers and self.state.is_ui_connected:
                self.state.is_ui_connected = False
                main_logger.info("[Host OS] CLI chat disconnected from the terminal.")
                await self.incoming_queue.put(("_CONNECTION_CLOSED", ""))

            try:
                writer.close()
                await writer.wait_closed()

            except Exception as e:
                main_logger.debug(f"[Host Terminal] Error closing client session: {e}")

    async def broadcast_message(self, text: str) -> None:
        """
        Asynchronous broadcasting of a message from the agent to all active TCP sessions (open consoles).
        Packs the text into JSON with a timestamp for parsing on the CLI widgets side.

        Args:
            text: Agent message text (supports Markdown).
        """

        time_str = get_now_formatted(self.timezone, "%Y-%m-%d %H:%M:%S")
        self._record_message(self.agent_name, text, time_str)

        if not self.active_writers:
            return

        # Pack to JSON along with the time for a nice output in CLI
        payload = json.dumps({"text": text, "time": time_str}, ensure_ascii=False) + "\n"
        data = payload.encode("utf-8")

        for writer in list(self.active_writers):
            try:
                writer.write(data)
                await writer.drain()
            except Exception:
                self.active_writers.discard(writer)

    def _record_message(self, sender: str, text: str, time_str: str = "") -> None:
        """Writes message to L0 State and the physical history file."""
        if not time_str:
            time_str = get_now_formatted(self.timezone, "%Y-%m-%d %H:%M:%S")

        self.state.add_message(sender, text, time_str)

        history = self._read_history_file()
        history.append({"time": time_str, "sender": sender, "text": text})

        if len(history) > self.config.history_limit:
            history = history[-self.config.history_limit :]

        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

    def _read_history_file(self) -> list:
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _load_history(self) -> None:
        """
        Pulls context history from the file on server restart.
        """

        history = self._read_history_file()
        recent = history[-self.config.context_limit :]
        for msg in recent:
            self.state.add_message(msg["sender"], msg["text"], msg.get("time", ""))

    async def get_context_block(self, **kwargs: Any) -> str:
        """Context provider for ContextRegistry."""
        desc = "Description: Direct CLI chat with the system operator/user."
        if not self.state.is_online:
            return f"### HOST TERMINAL [OFF] \n{desc}\nThe interface is disabled."

        ui_status = (
            "The terminal window is opened."
            if self.state.is_ui_connected
            else "The terminal window is closed."
        )
        return f"### HOST TERMINAL [ON]\n{desc}\nStatus: {ui_status}\n\nRecent messages:\n{self.state.formatted_messages}"

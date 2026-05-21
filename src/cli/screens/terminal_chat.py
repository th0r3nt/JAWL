"""
Terminal Chat CLI Screen.

Acts as the interactive operator terminal. Initiates safe handshake TCP client
connections to talk directly with the awake JAWL agent core.
"""

import asyncio
import json
import io
from pathlib import Path

import questionary
from prompt_toolkit import PromptSession, print_formatted_text, HTML
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.cli.widgets.ui import (
    print_error,
    print_info,
    print_success,
    clear_screen,
    draw_header,
    get_custom_style,
    launch_in_new_window,
    set_window_title,
)
from src.utils.settings import load_config
from src.cli.screens.agent_control import _is_agent_running

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def _print_markdown_safe(text: str) -> None:
    """Renders Rich markdown output safely."""
    formatted_text = text.replace("\n", "  \n")

    str_console = Console(file=io.StringIO(), force_terminal=True, color_system="standard")
    str_console.print(Markdown(formatted_text))
    ansi_str = str_console.file.getvalue()

    if ansi_str.endswith("\n"):
        ansi_str = ansi_str[:-1]

    print_formatted_text(ANSI(ansi_str))


async def _chat_loop(port: int, history_file: Path, agent_name: str) -> None:
    set_window_title(f"JAWL - Chat with agent {agent_name}")

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"JAWL_HANDSHAKE\n")
        await writer.drain()

    except ConnectionRefusedError:
        print_error("Failed to connect to chat.")
        print_info("Ensure the agent is running and the 'Host Terminal' interface is enabled.")
        print("\nPress Enter to return...")
        input()
        return

    clear_screen()

    Console().print(
        Panel(
            f"[bold cyan]Interactive chat with agent {agent_name}[/bold cyan]\n"
            "[dim]Send: Enter[/dim]\n"
            "[dim]Exit: /exit or Ctrl+C[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            for msg in history[-15:]:
                sender = msg.get("sender")
                text = msg.get("text", "")
                time_str = msg.get("time", "")

                time_prefix = f"<style fg='gray'>[{time_str}]</style> " if time_str else ""

                if sender == "User":
                    print_formatted_text(
                        HTML(f"{time_prefix}<ansigreen><b>You:</b></ansigreen> {text}")
                    )
                else:
                    print_formatted_text(
                        HTML(f"\n{time_prefix}<ansimagenta><b>{sender}:</b></ansimagenta>")
                    )
                    _print_markdown_safe(text)

            print_formatted_text(HTML("\n<style fg='gray'>--- End of History ---</style>\n"))
        except Exception:
            pass

    session = PromptSession()

    bindings = KeyBindings()

    @bindings.add("enter")
    def handle_enter(event):
        event.current_buffer.validate_and_handle()

    @bindings.add("escape", "enter")
    def handle_newline(event):
        event.current_buffer.insert_text("\n")

    def prompt_continuation(width, line_number, is_soft_wrap):
        return "... ".rjust(width)

    async def receive_messages():
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break

                raw_text = data.decode("utf-8", errors="replace").strip()
                if not raw_text:
                    continue

                time_str = ""
                try:
                    payload = json.loads(raw_text)
                    message_text = payload.get("text", "")
                    time_str = payload.get("time", "")
                except json.JSONDecodeError:
                    message_text = raw_text

                time_prefix = f"<style fg='gray'>[{time_str}]</style> " if time_str else ""

                with patch_stdout():
                    print_formatted_text(
                        HTML(f"\n{time_prefix}<ansimagenta><b>{agent_name}:</b></ansimagenta>")
                    )
                    _print_markdown_safe(message_text)
                    print("")

        except asyncio.CancelledError:
            pass

        except Exception as e:
            with patch_stdout():
                print_formatted_text(
                    HTML(f"\n<ansired><b>✗ Connection lost:</b> {e}</ansired>")
                )
                print_formatted_text(
                    HTML("<style fg='gray'>Type /exit or press Ctrl+C to exit.</style>\n")
                )

    receive_task = asyncio.create_task(receive_messages())

    try:
        while True:
            with patch_stdout():
                user_input = await session.prompt_async(
                    HTML("<ansigreen><b>You:</b></ansigreen> "),
                    multiline=True,
                    key_bindings=bindings,
                    prompt_continuation=prompt_continuation,
                )

            text = user_input.strip()

            try:
                text = text.encode("utf-8", errors="replace").decode("utf-8")
            except Exception:
                pass

            if not text:
                continue
            if text.lower() in ["/exit", "/quit"]:
                break

            payload = json.dumps({"text": text}, ensure_ascii=False)

            try:
                writer.write((payload + "\n").encode("utf-8"))
                await writer.drain()
            except (ConnectionError, OSError):
                with patch_stdout():
                    print_formatted_text(
                        HTML(
                            "\n<ansired><b>✗ Connection lost (Agent is rebooting or stopped).</b></ansired>"
                        )
                    )
                break

    except (KeyboardInterrupt, EOFError):
        pass

    finally:
        receive_task.cancel()
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


def terminal_chat_screen() -> None:
    set_window_title("JAWL - Terminal (Settings)")
    style = get_custom_style()

    while True:
        draw_header()
        choice = questionary.select(
            "Agent Chat:",
            choices=[
                questionary.Choice("[@] Open Chat", "open"),
                questionary.Choice("[-] Clear Chat History", "clear_history"),
                questionary.Separator(" "),
                questionary.Choice("↩ Back", "back"),
            ],
            style=style,
            qmark="",
            instruction="\n (Arrows ↑/↓ for navigation)\n",
        ).ask()

        if choice == "back" or choice is None:
            break
        if choice == "open":
            launch_in_new_window("--terminal")
        elif choice == "clear_history":
            _clear_terminal_history()


def _open_terminal_chat() -> None:
    if not _is_agent_running():
        print_error("Error: Agent is not running. Launch the main code first to communicate.")
        print("\nPress Enter to return.")
        input()
        return

    settings, interfaces = load_config()
    if not hasattr(interfaces.host, "terminal") or not interfaces.host.terminal.enabled:
        print_error(
            "The 'Host Terminal' interface is disabled in the settings (interfaces.yaml)."
        )
        print("\nPress Enter to return.")
        input()
        return

    base_dir = (
        ROOT_DIR / "src" / "utils" / "local" / "data" / "interfaces" / "host" / "terminal"
    )
    history_file = base_dir / "history.json"
    port_file = base_dir / "terminal.port"
    agent_name = settings.identity.agent_name

    if not port_file.exists():
        print_error("Terminal server is not running or an error occurred.")
        print("\nPress Enter to return.")
        input()
        return

    try:
        active_port = int(port_file.read_text().strip())
    except ValueError:
        print_error("Port file is corrupted.")
        input()
        return

    asyncio.run(_chat_loop(active_port, history_file, agent_name))


def _clear_terminal_history() -> None:
    base_dir = (
        ROOT_DIR / "src" / "utils" / "local" / "data" / "interfaces" / "host" / "terminal"
    )
    history_file = base_dir / "history.json"
    if history_file.exists():
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False)
            print_success("Terminal history successfully cleared.")

        except Exception as e:
            print_error(f"Failed to clear history: {e}")
    else:
        print_info(" History is already empty (file not found).")
    print("\nPress Enter to return.")
    input()

"""
Background monitoring of long-running agent processes (daemons) in the sandbox.

Tracks their status (alive/dead/zombie) and asynchronously gathers IPC webhooks (via file markers),
dispatching them to the global event bus.
"""

import asyncio
import time
import json
import psutil

from src.utils.logger import main_logger
from src.utils.dtime import seconds_to_duration_str
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient


class DaemonsPoller:
    """Monitoring of background scripts (daemons) and gathering of webhooks from the sandbox."""

    def __init__(self, client: HostOSClient, state: HostOSState, bus: EventBus):
        self.client = client
        self.state = state
        self.bus = bus
        self._is_running = False
        self._task: asyncio.Task | None = None

    def start(self):
        if not self._is_running:
            self._is_running = True
            self._task = asyncio.create_task(self._fast_loop())

    def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _fast_loop(self):
        """
        Fast loop (every second) for immediate reaction.
        """

        while self._is_running:
            try:
                await self._poll_sandbox_events()
                await self._update_daemons_status()

            except asyncio.CancelledError:
                break

            except Exception as e:
                main_logger.error(f"[Host OS] Error in daemons poller: {e}")

            await asyncio.sleep(1)

    async def _poll_sandbox_events(self):
        events_dir = self.client.events_dir
        if not events_dir.exists():
            return

        for file_path in events_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                msg = data.get("message", "Sandbox event.")
                payload = data.get("payload", {})

                # Check if this is a hidden system dashboard update
                # When updating the dashboard, this marker is always present in the payload
                if payload.get("_jawl_internal_type") == "dashboard_update":
                    await self.bus.publish(
                        Events.SYSTEM_DASHBOARD_UPDATE,
                        name=payload.get("name"),
                        content=payload.get("content"),
                    )
                else:
                    await self.bus.publish(
                        Events.HOST_OS_SANDBOX_EVENT, message=msg, **payload
                    )

            except Exception as e:
                main_logger.error(f"[Host OS] Error reading event from sandbox: {e}")

            finally:
                try:
                    file_path.unlink()
                except Exception:
                    pass

    async def _update_daemons_status(self):
        daemons = self.client.get_daemons_registry()
        if not daemons:
            self.state.active_daemons = "No running daemons."
            return

        lines = []
        modified = False
        dead_daemons = []

        for pid_str, info in list(daemons.items()):
            pid = int(pid_str)
            name = info.get("name", "Unknown")
            desc = info.get("description", "No description")
            start_time = info.get("start_time", time.time())

            is_alive = False
            if psutil.pid_exists(pid):
                try:
                    proc = psutil.Process(pid)
                    if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                        is_alive = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if is_alive:
                uptime = seconds_to_duration_str(time.time() - start_time)
                lines.append(
                    f"- [PID: {pid}] {name} (Uptime: {uptime})\n  Description: {desc}"
                )
            else:
                dead_daemons.append(name)
                del daemons[pid_str]
                modified = True

        if modified:
            self.client.set_daemons_registry(daemons)
            for d_name in dead_daemons:
                await self.bus.publish(
                    Events.HOST_OS_SANDBOX_EVENT,
                    message=f"Background script '{d_name}' finished execution.",
                    log_hint="It is recommended to check its log file (sandbox/logs/*.log) to find the cause.",
                )

        self.state.active_daemons = "\n".join(lines) if lines else "No running daemons."

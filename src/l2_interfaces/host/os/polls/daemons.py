"""
Фоновый мониторинг долгоживущих процессов (демонов) агента в песочнице.
Отслеживает их статус (жив/умер/зомби) и асинхронно собирает IPC-вебхуки (через файл-маркеры),
пробрасывая их в глобальную шину событий.
"""

import asyncio
import time
import json
import psutil

from src.utils.logger import system_logger
from src.utils.dtime import seconds_to_duration_str
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.l0_state.interfaces.host.os_state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient


class DaemonsPoller:
    """Мониторинг фоновых скриптов (демонов) и сбор вебхуков из песочницы."""

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
        Быстрый цикл (каждую секунду) для моментальной реакции.
        """

        while self._is_running:
            try:
                await self._poll_sandbox_events()
                await self._update_daemons_status()

            except asyncio.CancelledError:
                break

            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка в поллере демонов: {e}")

            await asyncio.sleep(1)

    async def _poll_sandbox_events(self):
        events_dir = self.client.events_dir
        if not events_dir.exists():
            return

        for file_path in events_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                msg = data.get("message", "Событие из песочницы.")
                payload = data.get("payload", {})

                # Проверяем, не является ли это скрытым системным обновлением дашборда
                # При обновлении дашборда в пейлоаде всегда идет это маркер
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
                system_logger.error(f"[Host OS] Ошибка чтения события из песочницы: {e}")

            finally:
                try:
                    file_path.unlink()
                except Exception:
                    pass

    async def _update_daemons_status(self):
        daemons = self.client.get_daemons_registry()
        if not daemons:
            self.state.active_daemons = "Нет запущенных демонов."
            return

        lines = []
        modified = False
        dead_daemons = []

        for pid_str, info in list(daemons.items()):
            pid = int(pid_str)
            name = info.get("name", "Unknown")
            desc = info.get("description", "Без описания")
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
                lines.append(f"- [PID: {pid}] {name} (Uptime: {uptime})\n  Описание: {desc}")
            else:
                dead_daemons.append(name)
                del daemons[pid_str]
                modified = True

        if modified:
            self.client.set_daemons_registry(daemons)
            for d_name in dead_daemons:
                await self.bus.publish(
                    Events.HOST_OS_SANDBOX_EVENT,
                    message=f"Фоновый скрипт '{d_name}' завершил работу (успешно или упал).",
                    log_hint="Рекомендуется проверить его лог-файл (sandbox/logs/daemon_*.log), чтобы узнать причину.",
                )

        self.state.active_daemons = "\n".join(lines) if lines else "Нет запущенных демонов."

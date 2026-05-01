import asyncio
import time
import socket
import psutil

from src.utils.logger import system_logger
from src.utils.dtime import get_now_formatted, seconds_to_duration_str
from src.l0_state.interfaces.host.os_state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient


class TelemetryPoller:
    """Сборщик системной телеметрии (CPU, RAM, Сеть, Время)."""

    def __init__(self, client: HostOSClient, state: HostOSState):
        self.client = client
        self.state = state
        self._is_running = False
        self._task: asyncio.Task | None = None

        # Инициализируем счетчик CPU
        psutil.cpu_percent(interval=None)

    def start(self):
        if not self._is_running:
            self._is_running = True
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        self.state.polling_interval = self.client.config.monitoring_interval_sec
        while self._is_running:
            try:
                self._update_datetime_and_uptime()
                self._update_telemetry()
                await self._update_network()
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка в цикле телеметрии: {e}")

            await asyncio.sleep(self.client.config.monitoring_interval_sec)

    def _update_datetime_and_uptime(self):
        self.state.datetime = get_now_formatted(self.client.timezone)
        boot_time = psutil.boot_time()
        self.state.uptime = seconds_to_duration_str(time.time() - boot_time)

    def _update_telemetry(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        ram_used_gb = round((mem.total - mem.available) / (1024**3), 1)

        processes = []
        for p in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                if p.info["memory_percent"]:
                    processes.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        limit = self.client.config.top_processes_limit
        top_procs = sorted(processes, key=lambda x: x["memory_percent"], reverse=True)[:limit]

        proc_strings = [
            f"{p['name']} (PID: {p['pid']}, {round(p['memory_percent'], 1)}%)"
            for p in top_procs
        ]
        top_str = ", ".join(proc_strings) if proc_strings else "Нет данных"

        self.state.telemetry = (
            f"CPU: {cpu}% ({self.state.cpu_name})\n"
            f"RAM: {ram_percent}% ({ram_used_gb} / {self.state.total_ram_gb} GB)\n"
            f"Топ процессов (RAM): {top_str}"
        )

    async def _update_network(self):
        def check_internet():
            try:
                with socket.create_connection(("1.1.1.1", 53), timeout=2):
                    return True
            except OSError:
                return False

        is_online = await asyncio.to_thread(check_internet)
        status = "Online" if is_online else "Offline"

        try:
            conns = len(psutil.net_connections(kind="inet"))
        except psutil.AccessDenied:
            conns = "Неизвестно"

        self.state.network = f"Internet: {status} | Соединений: {conns}"

import asyncio
import time
import socket
from datetime import datetime
import psutil

from src.utils.event.bus import EventBus
from src.utils.logger import system_logger

from src.l0_state.interfaces.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient


class HostOSEvents:
    """
    Фоновый мониторинг состояния ПК.
    Обновляет приборную панель агента (HostOSState) каждые 30 секунд.
    """

    def __init__(self, host_os_client: HostOSClient, state: HostOSState, event_bus: EventBus):
        self.host_os = host_os_client
        self.state = state
        self.bus = event_bus

        self._is_running = False
        self._monitoring_task: asyncio.Task | None = None

        # Храним предыдущий список файлов для поиска изменений
        self._last_sandbox_files = set()

        # Инициализируем CPU счетчик
        psutil.cpu_percent(interval=None)

    async def start(self):
        """Запускает фоновый цикл мониторинга."""

        if self._is_running:
            return

        self._is_running = True
        self._monitoring_task = asyncio.create_task(self._loop())

        system_logger.info("[System] Host OS мониторинг запущен.")

    async def stop(self):
        """Останавливает цикл."""

        self._is_running = False

        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None

        system_logger.info("[System] Host OS мониторинг остановлен.")

    async def _loop(self):
        """Бесконечный цикл поллинга."""

        while self._is_running:
            try:
                self._update_datetime_and_uptime()
                self._update_telemetry()
                await self._update_network()
                await self._check_sandbox()

            except asyncio.CancelledError:
                break

            except Exception as e:
                system_logger.error(f"[System] Ошибка в цикле мониторинга Host OS: {e}")

            # Спим перед следующим тиком
            await asyncio.sleep(self.host_os.config.monitoring_interval_sec)

    def _update_datetime_and_uptime(self):
        # Дата и время
        self.state.datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Аптайм
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if days > 0:
            self.state.uptime = f"{days} дней, {hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            self.state.uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _update_telemetry(self):
        # CPU и RAM
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent

        # Собираем топ процессов по ОЗУ
        processes = []
        for p in psutil.process_iter(["name", "memory_percent"]):
            try:
                if p.info["memory_percent"]:
                    processes.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        limit = self.host_os.config.top_processes_limit
        top_procs = sorted(processes, key=lambda x: x["memory_percent"], reverse=True)[:limit]

        proc_strings = [f"{p['name']} ({round(p['memory_percent'], 1)}%)" for p in top_procs]
        top_str = ", ".join(proc_strings) if proc_strings else "Нет данных"

        # Записываем в стейт агента
        self.state.telemetry = f"CPU: {cpu}%, RAM: {ram}%\nТоп процессов (RAM): {top_str}"

    async def _update_network(self):
        # Проверяем доступ к интернету через легкий сокет
        def check_internet():
            try:
                with socket.create_connection(("1.1.1.1", 53), timeout=2):
                    return True
            except OSError:
                return False

        is_online = await asyncio.to_thread(check_internet)
        status = "Online" if is_online else "Offline"

        # Считаем активные коннекты
        try:
            conns = len(psutil.net_connections(kind="inet"))
        except psutil.AccessDenied:
            conns = "Неизвестно"

        self.state.network = f"Internet: {status} | Соединений: {conns}"

    def _check_sandbox(self):
        sandbox = self.host_os.sandbox_dir

        # Получаем список всех относительных путей (рекурсивно) для поиска новых файлов
        current_paths = set(str(p.relative_to(sandbox)) for p in sandbox.rglob("*"))

        # Вычисляем разницу
        new_files = current_paths - self._last_sandbox_files
        if new_files:
            system_logger.info(
                f"[System] В песочнице появились новые файлы/папки: {', '.join(new_files)}"
            )

        # Строим красивое ASCII-дерево для приборной панели
        def build_tree(dir_path, prefix=""):
            lines = []
            try:
                # Сортируем: сначала папки, потом файлы (по алфавиту)
                items = sorted(
                    list(dir_path.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower())
                )
                for i, item in enumerate(items):
                    is_last = i == len(items) - 1
                    connector = "└── " if is_last else "├── "
                    lines.append(f"{prefix}{connector}{item.name}")

                    if item.is_dir():
                        extension = "    " if is_last else "│   "
                        lines.extend(build_tree(item, prefix + extension))
            except Exception:
                pass
            return lines

        tree_lines = build_tree(sandbox)

        # Защита контекста LLM: если в песочнице слишком много файлов, обрезаем вывод
        max_tree_lines = 200
        if len(tree_lines) > max_tree_lines:
            tree_lines = tree_lines[:max_tree_lines] + [
                f"└── ... [Дерево обрезано: показано {max_tree_lines} элементов]"
            ]

        # Сохраняем стейт
        if tree_lines:
            self.state.sandbox_files = "sandbox/\n" + "\n".join(tree_lines)
        else:
            self.state.sandbox_files = "Пусто"

        self._last_sandbox_files = current_paths

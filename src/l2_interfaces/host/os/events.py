import asyncio
import time
import socket
import platform
import subprocess
from pathlib import Path
import psutil
import json
from typing import Any

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.logger import system_logger
from src.utils.dtime import get_now_formatted, seconds_to_duration_str

from src.l0_state.interfaces.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient


def _get_cpu_name() -> str:
    """Безопасный кроссплатформенный метод получения названия CPU."""

    try:
        os_name = platform.system()

        if os_name == "Windows":
            return platform.processor()

        elif os_name == "Darwin":
            return (
                subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"])
                .strip()
                .decode()
            )

        elif os_name == "Linux":
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[1].strip()
    except Exception:
        pass
    # Фолбек, если что-то пошло не так
    return platform.processor() or "Unknown CPU"


class _SandboxWatchdogHandler(FileSystemEventHandler):
    """
    Обработчик событий watchdog.
    Так как watchdog работает в отдельном синхронном потоке,
    мы пробрасываем события в асинхронную очередь через run_coroutine_threadsafe.
    """

    def __init__(self, os_events_instance: "HostOSEvents", loop: asyncio.AbstractEventLoop):
        self.os_events = os_events_instance
        self.loop = loop

    def _trigger_event(self, event, sys_event_config):
        if event.is_directory:
            return

        if self.os_events._is_ignored(Path(event.src_path)):
            return

        # Безопасный вызов асинхронного метода из синхронного потока
        asyncio.run_coroutine_threadsafe(
            self.os_events.handle_file_system_event(sys_event_config, event.src_path),
            self.loop,
        )

    def on_created(self, event):
        self._trigger_event(event, Events.HOST_OS_FILE_CREATED)

    def on_modified(self, event):
        self._trigger_event(event, Events.HOST_OS_FILE_MODIFIED)

    def on_deleted(self, event):
        self._trigger_event(event, Events.HOST_OS_FILE_DELETED)

    def on_moved(self, event):
        if not event.is_directory:
            if not self.os_events._is_ignored(Path(event.dest_path)):
                asyncio.run_coroutine_threadsafe(
                    self.os_events.handle_file_system_event(
                        Events.HOST_OS_FILE_CREATED, event.dest_path
                    ),
                    self.loop,
                )


class HostOSEvents:
    """
    Фоновый мониторинг состояния ПК.
    Обновляет HostOSState.
    """

    def __init__(self, host_os_client: HostOSClient, state: HostOSState, event_bus: EventBus):
        self.host_os = host_os_client
        self.state = state
        self.bus = event_bus

        self._is_running: bool = False
        self._monitoring_task: asyncio.Task | None = None

        self._observer: Observer | None = None  # type: ignore
        self._watches: dict[str, Any] = {}

        self._persistence_file = (
            self.host_os.framework_dir
            / "src"
            / "utils"
            / "local"
            / "data"
            / "os"
            / "tracked_dirs.json"
        )

        self._last_sandbox_files = set()
        psutil.cpu_percent(interval=None)

        # Собираем статику 1 раз при старте
        self.state.os_info = f"{platform.system()} {platform.release()}"
        self.state.cpu_name = _get_cpu_name()
        self.state.total_ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)

    async def start(self) -> None:
        if self._is_running:
            return

        self._is_running = True

        # Тихая пред-индексация песочницы, чтобы не спамить логами о "новых" файлах при старте
        if self.host_os.sandbox_dir.exists():
            self._last_sandbox_files = set(
                str(p.relative_to(self.host_os.sandbox_dir))
                for p in self.host_os.sandbox_dir.rglob("*")
                if not self._is_ignored(p)
            )

        self._monitoring_task = asyncio.create_task(self._loop())

        # Запуск Watchdog
        self._observer = Observer()

        # Дефолтная песочница
        self.track_path(str(self.host_os.sandbox_dir), save=False)

        # Восстанавливаем кастомные пути
        for p in self._load_persisted_dirs():
            try:
                self.track_path(p, save=False)
            except Exception as e:
                system_logger.warning(
                    f"[Host OS] Не удалось восстановить отслеживание для {p}: {e}"
                )

        self._observer.start()
        system_logger.info("[Host OS] Мониторинг и файловый радар запущены.")

    async def stop(self) -> None:
        self._is_running = False

        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None

        if self._observer:
            self._observer.stop()
            await asyncio.to_thread(self._observer.join)
            self._observer = None
            self._watches.clear()

        system_logger.info("[Host OS] Мониторинг остановлен.")
        self.state.is_online = False

    # ==========================================================
    # КАСТОМНЫЕ ДИРЕКТОРИИ
    # ==========================================================

    def track_path(self, path_str: str, save: bool = True) -> bool:
        """Регистрирует путь в Watchdog."""

        if path_str in self._watches:
            return False

        path_obj = Path(path_str)
        if not path_obj.exists() or not path_obj.is_dir():
            raise ValueError(f"Путь не существует или не является директорией: {path_str}")

        handler = _SandboxWatchdogHandler(self, asyncio.get_running_loop())
        watch = self._observer.schedule(handler, path_str, recursive=True)
        self._watches[path_str] = watch

        if save:
            self._save_persisted_dirs()
        return True

    def untrack_path(self, path_str: str) -> bool:
        """Удаляет путь из Watchdog."""

        if path_str not in self._watches:
            return False
        if path_str == str(self.host_os.sandbox_dir):
            raise ValueError(
                "Отказано в доступе: запрещено отключать мониторинг корневой песочницы."
            )

        watch = self._watches.pop(path_str)
        self._observer.unschedule(watch)
        self._save_persisted_dirs()
        return True

    def _save_persisted_dirs(self):
        self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
        # Не сохраняем дефолтную песочницу, только кастомные пути
        paths = [p for p in self._watches.keys() if p != str(self.host_os.sandbox_dir)]
        with open(self._persistence_file, "w", encoding="utf-8") as f:
            json.dump(paths, f, indent=4)

    def _load_persisted_dirs(self) -> list:
        if not self._persistence_file.exists():
            return []
        try:
            with open(self._persistence_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    # ==========================================================
    # ПОЛЛИНГ
    # ==========================================================

    async def handle_file_system_event(self, sys_event_config, filepath: str):
        """Вызывается мгновенно при любом изменении файла (создание/удаление/изменение)."""
        # Сразу перестраиваем ASCII-дерево в стейте, чтобы агент увидел актуальную картину
        self._check_sandbox()

        try:
            rel_path = str(Path(filepath).relative_to(self.host_os.sandbox_dir))
        except ValueError:
            rel_path = str(filepath)

        # Публикуем событие
        await self.bus.publish(sys_event_config, filepath=rel_path)

    async def _loop(self):
        """Бесконечный цикл поллинга для телеметрии (раз в 20-30 сек)."""
        self.state.polling_interval = self.host_os.config.monitoring_interval_sec

        while self._is_running:
            try:
                self._update_datetime_and_uptime()
                self._update_telemetry()
                await self._update_network()
                # Мы всё равно периодически чекаем песочницу на случай, если watchdog что-то пропустил
                self._check_sandbox()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка в цикле мониторинга: {e}")

            await asyncio.sleep(self.host_os.config.monitoring_interval_sec)

    def _is_ignored(self, path: Path) -> bool:
        """Единый фильтр мусора. Отсекает кэш, логи, скрытые файлы и виртуальные окружения."""

        ignore_dirs = {
            "__pycache__",
            ".pytest_cache",
            "node_modules",
            "venv",
            ".venv",
            "env",
            ".git",
        }
        ignore_exts = {".pyc", ".pyo", ".pyd", ".tmp", ".swp"}

        if path.suffix in ignore_exts or path.name.endswith("~"):
            return True

        for part in path.parts:
            if part in ignore_dirs:
                return True
            # Игнорируем скрытые папки/файлы, но оставляем .env на случай, если он нужен в песочнице
            if part.startswith(".") and part not in {".", ".env"}:
                return True

        return False

    def _update_datetime_and_uptime(self):
        self.state.datetime = get_now_formatted(self.host_os.timezone)
        boot_time = psutil.boot_time()
        self.state.uptime = seconds_to_duration_str(time.time() - boot_time)

    def _update_telemetry(self):
        cpu = psutil.cpu_percent(interval=None)

        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        ram_used_gb = round((mem.total - mem.available) / (1024**3), 1)

        # Собираем топ процессов по ОЗУ
        processes = []
        for p in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                if p.info["memory_percent"]:
                    processes.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        limit = self.host_os.config.top_processes_limit
        top_procs = sorted(processes, key=lambda x: x["memory_percent"], reverse=True)[:limit]

        proc_strings = [
            f"{p['name']} (PID: {p['pid']}, {round(p['memory_percent'], 1)}%)"
            for p in top_procs
        ]
        top_str = ", ".join(proc_strings) if proc_strings else "Нет данных"

        # === Обновляем вывод телеметрии ===
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

        # Считаем активные коннекты
        try:
            conns = len(psutil.net_connections(kind="inet"))
        except psutil.AccessDenied:
            conns = "Неизвестно"

        self.state.network = f"Internet: {status} | Соединений: {conns}"

    def _check_sandbox(self):
        sandbox = self.host_os.sandbox_dir

        # Собираем только те файлы, которые не попадают под фильтр
        current_paths = set(
            str(p.relative_to(sandbox)) for p in sandbox.rglob("*") if not self._is_ignored(p)
        )

        new_files = current_paths - self._last_sandbox_files
        if new_files:
            system_logger.info(
                f"[Host OS] В песочнице появились новые файлы/папки: {', '.join(new_files)}"
            )

        def build_tree(dir_path, prefix=""):
            lines = []
            try:
                # Фильтруем папки и файлы перед построением дерева
                items = [item for item in dir_path.iterdir() if not self._is_ignored(item)]
                items = sorted(items, key=lambda x: (not x.is_dir(), x.name.lower()))
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

        max_tree_lines = 200
        if len(tree_lines) > max_tree_lines:
            tree_lines = tree_lines[:max_tree_lines] + [
                f"└── ...[Дерево обрезано: показано {max_tree_lines} элементов]"
            ]

        if tree_lines:
            self.state.sandbox_files = "sandbox/\n" + "\n".join(tree_lines)
        else:
            self.state.sandbox_files = "Пусто"

        self._last_sandbox_files = current_paths

import asyncio
import time
import socket
import platform
import subprocess
from pathlib import Path
import psutil
import json
import difflib
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
        self._fast_monitoring_task: asyncio.Task | None = None

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

        self._batch_queue: dict[str, Any] = {}
        self._batch_task: asyncio.Task | None = None
        self._batch_delay: float = 2.0  # Окно сбора массовых изменений (в секундах)

        self._file_cache: dict[str, str] = {}
        self._diff_size_limit = 1024 * 100  # Макс 100 КБ для кэша одного текстового файла

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
        self._fast_monitoring_task = asyncio.create_task(self._fast_loop())

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

        if self._fast_monitoring_task:
            self._fast_monitoring_task.cancel()
            self._fast_monitoring_task = None

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
    # ПОЛЛИНГ И WATCHDOG
    # ==========================================================

    async def handle_file_system_event(self, sys_event_config, filepath: str):
        """Вызывается при изменении файла. Группирует события для защиты от спама."""

        self._batch_queue[filepath] = sys_event_config

        # Запускаем таймер окна батчинга, если он еще не запущен
        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._process_batch())

    async def _process_batch(self):
        """Ожидает окончания бури событий и отправляет суммарный рапорт."""

        await asyncio.sleep(self._batch_delay)

        queue_snapshot = self._batch_queue.copy()
        self._batch_queue.clear()

        if not queue_snapshot:
            return

        # Перестраиваем ASCII дерево для стейта один раз на весь батч
        self._update_file_trees()

        # Если файлов больше 5 - группируем в одно событие (спасаем контекст агента)
        if len(queue_snapshot) > 5:
            created = sum(
                1 for e in queue_snapshot.values() if e == Events.HOST_OS_FILE_CREATED
            )
            modified = sum(
                1 for e in queue_snapshot.values() if e == Events.HOST_OS_FILE_MODIFIED
            )
            deleted = sum(
                1 for e in queue_snapshot.values() if e == Events.HOST_OS_FILE_DELETED
            )

            msg = f"Массовая файловая операция в песочнице. Создано: {created}, Изменено: {modified}, Удалено: {deleted}."

            # Тихо чистим кэш удаленных файлов
            for fp, ev in queue_snapshot.items():
                if ev == Events.HOST_OS_FILE_DELETED:
                    self._file_cache.pop(fp, None)

            await self.bus.publish(
                Events.HOST_OS_FILE_MODIFIED, filepath="[Массив файлов]", message=msg
            )
            return

        # Если файлов мало - обрабатываем индивидуально с генерацией diff
        for filepath, sys_event_config in queue_snapshot.items():
            await self._publish_single_file_event(filepath, sys_event_config)

    async def _publish_single_file_event(self, filepath: str, sys_event_config):
        """Обрабатывает единичный файл, генерирует diff и отправляет агенту."""
        try:
            rel_path = str(Path(filepath).relative_to(self.host_os.sandbox_dir))
        except ValueError:
            rel_path = str(filepath)

        diff_msg = ""
        path_obj = Path(filepath)

        # Если файл удален - чистим кэш
        if sys_event_config == Events.HOST_OS_FILE_DELETED:
            self._file_cache.pop(filepath, None)

        # Если создан или изменен - считаем символы
        elif path_obj.exists() and path_obj.is_file():
            try:
                size = path_obj.stat().st_size
                if size < self._diff_size_limit:
                    with open(path_obj, "r", encoding="utf-8") as f:
                        new_content = f.read()

                    old_content = self._file_cache.get(filepath)

                    if old_content is not None and old_content != new_content:
                        matcher = difflib.SequenceMatcher(None, old_content, new_content)
                        added = 0
                        deleted = 0
                        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                            if tag == "insert":
                                added += j2 - j1
                            elif tag == "delete":
                                deleted += i2 - i1
                            elif tag == "replace":
                                deleted += i2 - i1
                                added += j2 - j1

                        if added > 0 or deleted > 0:
                            limit = self.host_os.config.file_diff_max_chars

                            diff_gen = difflib.unified_diff(
                                old_content.splitlines(),
                                new_content.splitlines(),
                                n=1,
                                lineterm="",
                            )

                            diff_lines = [
                                line
                                for line in diff_gen
                                if not line.startswith("---") and not line.startswith("+++")
                            ]

                            diff_str = "\n".join(diff_lines)

                            # ========================================================
                            # СОХРАНЕНИЕ DIFF ДЛЯ КОНТЕКСТА АГЕНТА

                            if diff_str:
                                time_str = get_now_formatted(self.host_os.timezone, "%H:%M:%S")
                                diff_record = f"[{time_str}] {rel_path}:\n```diff\n{diff_str[:limit]}\n```"
                                self.state.recent_file_changes.insert(0, diff_record)
                                
                                # Берем лимит из конфига
                                limit_changes = self.host_os.config.recent_file_changes_limit
                                if len(self.state.recent_file_changes) > limit_changes:
                                    self.state.recent_file_changes.pop()
                                    
                            if len(diff_str) > limit:
                                diff_str = diff_str[:limit] + "\n... [Diff обрезан]"

                            diff_block = (
                                f"\n\nDiff preview:\n```diff\n{diff_str}\n```"
                                if diff_str
                                else ""
                            )
                            diff_msg = (
                                f"(Изменения: +{added} симв. / -{deleted} симв.){diff_block}"
                            )
                        else:
                            diff_msg = "(Сохранен без изменений текста)"

                    elif old_content is None:
                        diff_msg = f"(Зафиксирован: {size} байт)"

                    # Обновляем кэш
                    self._file_cache[filepath] = new_content
            except UnicodeDecodeError:
                pass
            except Exception:
                pass

        action_word = "изменен"
        if sys_event_config == Events.HOST_OS_FILE_CREATED:
            action_word = "создан"
        elif sys_event_config == Events.HOST_OS_FILE_DELETED:
            action_word = "удален"

        message = f"Файл '{rel_path}' был {action_word}. {diff_msg}".strip()

        await self.bus.publish(sys_event_config, filepath=rel_path, message=message)

    async def _loop(self):
        """Бесконечный цикл поллинга для телеметрии (раз в 20-30 сек)."""
        self.state.polling_interval = self.host_os.config.monitoring_interval_sec

        while self._is_running:
            try:
                self._update_datetime_and_uptime()
                self._update_telemetry()
                await self._update_network()
                # Мы всё равно периодически чекаем песочницу на случай, если watchdog что-то пропустил
                self._update_file_trees()

            except asyncio.CancelledError:
                break

            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка в цикле мониторинга: {e}")

            await asyncio.sleep(self.host_os.config.monitoring_interval_sec)

    async def _fast_loop(self):
        """Быстрый цикл (каждую секунду) для моментальной реакции на события демонов."""
        while self._is_running:

            try:
                await self._poll_sandbox_events()
                await self._update_daemons_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка в быстром цикле мониторинга: {e}")

            await asyncio.sleep(1)

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

    def _build_tree(
        self,
        dir_path: Path,
        use_emojis: bool,
        max_depth: int,
        current_depth: int = 0,
        prefix: str = "",
    ) -> list:
        meta = self.host_os.get_file_metadata()
        lines = []

        try:
            items = [item for item in dir_path.iterdir() if not self._is_ignored(item)]
            items = sorted(items, key=lambda x: (not x.is_dir(), x.name.lower()))

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└── " if is_last else "├── "

                icon = ""
                if use_emojis:
                    icon = "📂 " if item.is_dir() else "📄 "

                desc = ""
                if item.is_file():
                    try:
                        rel_path = item.relative_to(self.host_os.sandbox_dir).as_posix()
                        if rel_path in meta:
                            desc = f" — [{meta[rel_path]}]"
                    except ValueError:
                        pass  # Файл вне песочницы, метаданных нет

                # Папка sandbox/ выводится отдельным блоком - проверяем, чтобы не дублировать

                is_sandbox = item == self.host_os.sandbox_dir
                is_truncated_dir = item.is_dir() and current_depth >= max_depth

                if is_sandbox:
                    display_name = f"{item.name}/ [См. блок Sandbox Directory выше]"
                    should_traverse = False
                elif is_truncated_dir:
                    display_name = f"{item.name}/..."
                    should_traverse = False
                else:
                    display_name = item.name
                    should_traverse = item.is_dir()

                lines.append(f"{prefix}{connector}{icon}{display_name}{desc}")

                if should_traverse:
                    extension = "    " if is_last else "│   "
                    lines.extend(
                        self._build_tree(
                            item,
                            use_emojis,
                            max_depth,
                            current_depth + 1,
                            prefix + extension,
                        )
                    )
        except Exception:
            pass

        return lines

    def _update_file_trees(self):
        sandbox = self.host_os.sandbox_dir

        current_paths = set(
            str(p.relative_to(sandbox)) for p in sandbox.rglob("*") if not self._is_ignored(p)
        )

        new_files = current_paths - self._last_sandbox_files
        if new_files:
            system_logger.info(
                f"[Host OS] В песочнице появились новые файлы/папки: {', '.join(new_files)}"
            )

        # 1. Строим дерево песочницы (без лимита глубины, без эмодзи)
        sandbox_lines = self._build_tree(sandbox, use_emojis=False, max_depth=99)

        max_tree_lines = 200
        if len(sandbox_lines) > max_tree_lines:
            sandbox_lines = sandbox_lines[:max_tree_lines] + [
                f"└── ...[Дерево обрезано: показано {max_tree_lines} элементов]"
            ]

        if sandbox_lines:
            self.state.sandbox_files = "sandbox/\n" + "\n".join(sandbox_lines)
        else:
            self.state.sandbox_files = "Пусто"

        self._last_sandbox_files = current_paths

        # 2. Строим дерево фреймворка (JAWL Directory), если права позволяют
        if self.host_os.access_level >= 1:
            fw_dir = self.host_os.framework_dir
            fw_depth = self.host_os.config.framework_tree_depth
            fw_lines = self._build_tree(fw_dir, use_emojis=True, max_depth=fw_depth)

            if len(fw_lines) > max_tree_lines:
                fw_lines = fw_lines[:max_tree_lines] + [
                    f"└── ...[Дерево обрезано: показано {max_tree_lines} элементов]"
                ]

            if fw_lines:
                self.state.framework_files = f"🏠 {fw_dir.name}/\n" + "\n".join(fw_lines)
            else:
                self.state.framework_files = "Пусто"
        else:
            self.state.framework_files = ""

    async def _poll_sandbox_events(self):
        """
        Проверяет папку .jawl_events на наличие пингов от фоновых скриптов.
        """

        events_dir = self.host_os.events_dir
        if not events_dir.exists():
            return

        for file_path in events_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                msg = data.get("message", "Событие из песочницы.")
                payload = data.get("payload", {})

                await self.bus.publish(Events.HOST_OS_SANDBOX_EVENT, message=msg, **payload)
            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка чтения события из песочницы: {e}")
            finally:
                try:
                    file_path.unlink()
                except Exception:
                    pass

    async def _update_daemons_status(self):
        """
        Пингует процессы демонов, обновляет их Uptime или удаляет упавшие.
        """

        daemons = self.host_os.get_daemons_registry()
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
            self.host_os.set_daemons_registry(daemons)
            for d_name in dead_daemons:
                await self.bus.publish(
                    Events.HOST_OS_SANDBOX_EVENT,
                    message=f"Фоновый скрипт '{d_name}' завершил работу (успешно или упал).",
                    log_hint="Проверьте его лог-файл (sandbox/daemon_*.log), чтобы узнать причину.",
                )

        if lines:
            self.state.active_daemons = "\n".join(lines)
        else:
            self.state.active_daemons = "Нет запущенных демонов."

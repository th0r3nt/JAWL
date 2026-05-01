"""
Асинхронный агрегатор файловых событий на базе Watchdog.
Группирует массовые спам-события (создание/удаление) в батчи.
Вычисляет Git-подобные Diff-ы (добавлено/удалено строк) для текстовых файлов и инжектит их в L0 State.
"""

import asyncio
import difflib
import json
from pathlib import Path
from typing import Any

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.logger import system_logger
from src.utils.dtime import get_now_formatted

from src.l0_state.interfaces.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.polls.utils import is_ignored
from src.l2_interfaces.host.os.polls.tree_builder import TreeBuilder


class _SandboxWatchdogHandler(FileSystemEventHandler):
    """Пробрасывает события Watchdog в асинхронный цикл FileWatcher."""

    def __init__(self, watcher_instance: "FileWatcher", loop: asyncio.AbstractEventLoop):
        self.watcher = watcher_instance
        self.loop = loop

    def _trigger_event(self, event, sys_event_config):
        if event.is_directory:
            return

        if is_ignored(Path(event.src_path)):
            return

        asyncio.run_coroutine_threadsafe(
            self.watcher.handle_file_system_event(sys_event_config, event.src_path),
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
            if not is_ignored(Path(event.dest_path)):
                asyncio.run_coroutine_threadsafe(
                    self.watcher.handle_file_system_event(
                        Events.HOST_OS_FILE_CREATED, event.dest_path
                    ),
                    self.loop,
                )


class FileWatcher:
    """Мониторинг файловой системы (Watchdog, генерация Diff-ов, построение деревьев)."""

    def __init__(self, client: HostOSClient, state: HostOSState, bus: EventBus):
        self.client = client
        self.state = state
        self.bus = bus
        self.tree_builder = TreeBuilder(client)

        self._is_running = False
        self._task: asyncio.Task | None = None
        self._observer: Observer | None = None  # type: ignore
        self._watches: dict[str, Any] = {}

        self._persistence_file = (
            self.client.framework_dir
            / "src"
            / "utils"
            / "local"
            / "data"
            / "interfaces"
            / "host"
            / "os"
            / "tracked_dirs.json"
        )

        self._last_sandbox_files = set()
        self._batch_queue: dict[str, Any] = {}
        self._batch_task: asyncio.Task | None = None
        self._batch_delay: float = 2.0  # Окно группировки событий

        self._file_cache: dict[str, str] = {}
        self._diff_size_limit = 1024 * 100  # Макс 100 КБ для кэша одного файла

    def start(self):
        if self._is_running:
            return
        self._is_running = True

        if self.client.sandbox_dir.exists():
            self._last_sandbox_files = set(
                str(p.relative_to(self.client.sandbox_dir))
                for p in self.client.sandbox_dir.rglob("*")
                if not is_ignored(p)
            )

        self._observer = Observer()
        self.track_path(str(self.client.sandbox_dir), save=False)

        for p in self._load_persisted_dirs():
            try:
                self.track_path(p, save=False)
            except Exception as e:
                system_logger.warning(
                    f"[Host OS] Не удалось восстановить отслеживание для {p}: {e}"
                )

        self._observer.start()
        self._task = asyncio.create_task(self._slow_loop())

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            self._task = None

        if self._observer:
            self._observer.stop()
            await asyncio.to_thread(self._observer.join)
            self._observer = None
            self._watches.clear()

    def track_path(self, path_str: str, save: bool = True) -> bool:
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
        if path_str not in self._watches:
            return False
        if path_str == str(self.client.sandbox_dir):
            raise ValueError(
                "Отказано в доступе: запрещено отключать мониторинг корневой песочницы."
            )

        watch = self._watches.pop(path_str)
        self._observer.unschedule(watch)
        self._save_persisted_dirs()
        return True

    def _save_persisted_dirs(self):
        self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
        paths = [p for p in self._watches.keys() if p != str(self.client.sandbox_dir)]
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

    async def _slow_loop(self):
        """Резервный поллинг файловой системы (на случай пропуска событий Watchdog)."""
        while self._is_running:
            try:
                self._update_file_trees()
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка в медленном цикле файлов: {e}")
            await asyncio.sleep(self.client.config.monitoring_interval_sec)

    async def handle_file_system_event(self, sys_event_config, filepath: str):
        self._batch_queue[filepath] = sys_event_config
        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._process_batch())

    async def _process_batch(self):
        await asyncio.sleep(self._batch_delay)
        queue_snapshot = self._batch_queue.copy()
        self._batch_queue.clear()

        if not queue_snapshot:
            return

        self._update_file_trees()

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
            for fp, ev in queue_snapshot.items():
                if ev == Events.HOST_OS_FILE_DELETED:
                    self._file_cache.pop(fp, None)
                    # Вычисляем относительный путь и чистим метаданные
                    try:
                        rel_path = str(Path(fp).relative_to(self.client.sandbox_dir))
                    except ValueError:
                        rel_path = str(fp)
                    self.client.remove_file_metadata(rel_path)

            await self.bus.publish(
                Events.HOST_OS_FILE_MODIFIED, filepath="[Массив файлов]", message=msg
            )
            return

        for filepath, sys_event_config in queue_snapshot.items():
            await self._publish_single_file_event(filepath, sys_event_config)

    async def _publish_single_file_event(self, filepath: str, sys_event_config):
        try:
            rel_path = str(Path(filepath).relative_to(self.client.sandbox_dir))
        except ValueError:
            rel_path = str(filepath)

        diff_msg = ""
        path_obj = Path(filepath)

        if sys_event_config == Events.HOST_OS_FILE_DELETED:
            self._file_cache.pop(filepath, None)
            self.client.remove_file_metadata(rel_path)

        elif path_obj.exists() and path_obj.is_file():
            try:
                size = path_obj.stat().st_size
                if size < self._diff_size_limit:
                    with open(path_obj, "r", encoding="utf-8") as f:
                        new_content = f.read()

                    old_content = self._file_cache.get(filepath)
                    if old_content is not None and old_content != new_content:
                        matcher = difflib.SequenceMatcher(None, old_content, new_content)
                        added = deleted = 0
                        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                            if tag == "insert":
                                added += j2 - j1
                            elif tag == "delete":
                                deleted += i2 - i1
                            elif tag == "replace":
                                deleted += i2 - i1
                                added += j2 - j1

                        if added > 0 or deleted > 0:
                            limit = self.client.config.file_diff_max_chars
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

                            if diff_str:
                                time_str = get_now_formatted(self.client.timezone, "%H:%M:%S")
                                diff_record = f"[{time_str}] {rel_path}:\n```diff\n{diff_str[:limit]}\n```"
                                self.state.recent_file_changes.insert(0, diff_record)

                                limit_changes = self.client.config.recent_file_changes_limit
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

                    self._file_cache[filepath] = new_content
            except (UnicodeDecodeError, Exception):
                pass

        action_word = (
            "создан" if sys_event_config == Events.HOST_OS_FILE_CREATED else "изменен"
        )
        if sys_event_config == Events.HOST_OS_FILE_DELETED:
            action_word = "удален"

        message = f"Файл '{rel_path}' был {action_word}. {diff_msg}".strip()
        await self.bus.publish(sys_event_config, filepath=rel_path, message=message)

    def _update_file_trees(self):
        sandbox = self.client.sandbox_dir
        current_paths = set(
            str(p.relative_to(sandbox)) for p in sandbox.rglob("*") if not is_ignored(p)
        )

        new_files = current_paths - self._last_sandbox_files
        if new_files:
            system_logger.info(
                f"[Host OS] В песочнице появились новые файлы/папки: {', '.join(new_files)}"
            )

        sandbox_lines = self.tree_builder.build_tree(sandbox, use_emojis=False, max_depth=99)
        max_tree_lines = 200

        if len(sandbox_lines) > max_tree_lines:
            sandbox_lines = sandbox_lines[:max_tree_lines] + [
                f"└── ...[Дерево обрезано: показано {max_tree_lines} элементов]"
            ]

        self.state.sandbox_files = (
            "sandbox/\n" + "\n".join(sandbox_lines) if sandbox_lines else "Пусто"
        )
        self._last_sandbox_files = current_paths

        if self.client.access_level >= HostOSAccessLevel.OBSERVER:
            fw_dir = self.client.framework_dir
            fw_depth = self.client.config.framework_tree_depth
            fw_lines = self.tree_builder.build_tree(
                fw_dir, use_emojis=True, max_depth=fw_depth
            )

            if len(fw_lines) > max_tree_lines:
                fw_lines = fw_lines[:max_tree_lines] + [
                    f"└── ...[Дерево обрезано: показано {max_tree_lines} элементов]"
                ]

            self.state.framework_files = (
                f"🏠 {fw_dir.name}/\n" + "\n".join(fw_lines) if fw_lines else "Пусто"
            )
        else:
            self.state.framework_files = ""

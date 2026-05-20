"""
Управление виртуальным рабочим пространством (Workspace) агента.
Реализует концепцию "вкладок редактора", которые постоянно инжектятся в системный промпт.
"""

from src.utils.logger import main_logger

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSWorkspace:
    """Навыки для управления вкладками редактора агента."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def open_file(self, filepath: str) -> SkillResult:
        """
        Opens file in workspace. 
        Content remains injected into system prompt. 
        Critical for context retention.
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)
            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл не найден ({filepath}).")

            # Сохраняем относительный путь для универсальности
            try:
                rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()
            except ValueError:
                rel_path = safe_path.as_posix()

            limit = self.host_os.config.workspace_max_opened_files
            if len(self.host_os.state.opened_workspace_files) >= limit:
                return SkillResult.fail(
                    f"Ошибка: Открыто максимальное количество файлов ({limit}). Рекомендуется закрыть ненужные."
                )

            self.host_os.state.opened_workspace_files.add(rel_path)
            main_logger.info(f"[Host OS] Файл '{rel_path}' открыт в рабочей среде.")

            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при открытии файла: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def close_file(self, filepath: str) -> SkillResult:
        """
        Closes file, removing it from system prompt.
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)
            try:
                rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()
            except ValueError:
                rel_path = safe_path.as_posix()

            if rel_path in self.host_os.state.opened_workspace_files:
                self.host_os.state.opened_workspace_files.remove(rel_path)
                main_logger.info(f"[Host OS] Файл '{rel_path}' закрыт.")
                return SkillResult.ok("True")
            else:
                return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при закрытии файла: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def open_directory_workspace(
        self, path: str = ".", recursive: bool = False
    ) -> SkillResult:
        """
        Mass-opens directory files in workspace. 
        Highly recommended for keeping folder logic in context. 
        
        recursive: Includes subfolders.
        """
        try:
            safe_path = self.host_os.validate_path(path, is_write=False)
            if not safe_path.is_dir():
                return SkillResult.fail(f"Ошибка: Путь не является директорией ({path}).")

            limit = self.host_os.config.workspace_max_opened_files
            current_opened = len(self.host_os.state.opened_workspace_files)

            if current_opened >= limit:
                return SkillResult.fail(
                    f"Ошибка: Уже открыто максимальное количество файлов ({limit}). Сначала закрой ненужные с помощью close_file."
                )

            ignore_exts = {
                ".pyc",
                ".pyo",
                ".pyd",
                ".tmp",
                ".swp",
                ".exe",
                ".dll",
                ".so",
                ".png",
                ".jpg",
                ".jpeg",
                ".zip",
                ".tar",
                ".gz",
                ".db",
                ".sqlite",
                ".sqlite3",
                ".pdf",
                ".mp4",
                ".mp3",
                ".wav",
                ".class",
            }

            ignore_dirs = {
                ".git",
                "venv",
                ".venv",
                "env",
                "__pycache__",
                "node_modules",
                ".pytest_cache",
            }

            opened_now = []
            skipped_limit = 0

            iterator = safe_path.rglob("*") if recursive else safe_path.iterdir()

            # Сортируем пути для детерминированного порядка открытия
            items = sorted([p for p in iterator if p.is_file()])

            for item in items:
                # Пропускаем скрытые файлы и бинарники
                if item.name.startswith(".") or item.suffix.lower() in ignore_exts:
                    continue

                # При рекурсивном обходе пропускаем мусорные папки
                if recursive:
                    rel_to_base = item.relative_to(safe_path)
                    if any(
                        part in ignore_dirs or part.startswith(".")
                        for part in rel_to_base.parts
                    ):
                        continue

                if len(self.host_os.state.opened_workspace_files) >= limit:
                    skipped_limit += 1
                    continue

                try:
                    rel_path = item.relative_to(self.host_os.sandbox_dir).as_posix()
                except ValueError:
                    rel_path = item.as_posix()

                if rel_path not in self.host_os.state.opened_workspace_files:
                    self.host_os.state.opened_workspace_files.add(rel_path)
                    opened_now.append(item.name)

            if not opened_now:
                msg = "Не найдено подходящих текстовых файлов для открытия (или все они уже открыты)."
                if skipped_limit > 0:
                    msg += f" Пропущено из-за лимита: {skipped_limit} файлов."
                return SkillResult.ok("True")

            main_logger.info(
                f"[Host OS] Массово открыты файлы из '{safe_path.name}' в рабочей среде (рекурсивно: {recursive})."
            )

            msg = f"Успешно добавлены во вкладки: {', '.join(opened_now)}."
            if skipped_limit > 0:
                msg += f" (Пропущено из-за лимита открытых файлов: {skipped_limit})"

            return SkillResult.ok(msg)

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при открытии директории: {e}")

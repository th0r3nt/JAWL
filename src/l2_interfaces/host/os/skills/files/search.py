"""
Навыки поиска файлов и генерации дерева директорий.
"""

import asyncio
from pathlib import Path

from src.utils.logger import system_logger
from src.utils._tools import format_size

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class HostOSSearch:
    """Навыки поиска и ревизии файловой структуры."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def list_directory(self, path: str = ".", max_depth: int = 1) -> SkillResult:
        """
        Показывает содержимое директории.
        Args:
            max_depth: насколько глубоко заглядывать во вложенные папки (0 - только текущая папка, 1 - на один уровень вглубь, и т.д.)
        """
        limit = self.host_os.config.file_list_limit

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail(f"Ошибка: Путь не является директорией ({path}).")

            # Вычисляем понятный агенту путь от корня проекта
            try:
                dir_display = safe_path.relative_to(self.host_os.framework_dir).as_posix()
            except ValueError:
                dir_display = safe_path.name

            meta = self.host_os.get_file_metadata()

            ignore_exts = {".pyc", ".pyo", ".pyd", ".tmp", ".swp"}
            ignore_dirs = {
                ".git",
                "venv",
                ".venv",
                "env",
                "__pycache__",
                "node_modules",
                ".pytest_cache",
            }

            lines = []
            lines_count = 0

            def _build_tree(current_dir: Path, current_depth: int, prefix: str):
                nonlocal lines_count
                if current_depth > max_depth or lines_count >= limit:
                    return

                try:
                    items = []
                    for p in current_dir.iterdir():
                        if p.name.startswith(".") and p.name not in {".env"}:
                            continue
                        if p.is_dir() and p.name in ignore_dirs:
                            continue
                        if p.is_file() and p.suffix.lower() in ignore_exts:
                            continue
                        items.append(p)

                    # Сортировка: папки сначала, затем файлы (по алфавиту)
                    items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
                    total_items = len(items)

                    for i, item in enumerate(items):
                        if lines_count >= limit:
                            return

                        is_last = i == total_items - 1
                        connector = "└── " if is_last else "├── "

                        if item.is_dir():
                            lines.append(f"{prefix}{connector}📂 {item.name}/")
                            lines_count += 1

                            if current_depth < max_depth:
                                extension = "    " if is_last else "│   "
                                _build_tree(item, current_depth + 1, prefix + extension)
                        else:
                            try:
                                size_str = format_size(item.stat().st_size)
                            except Exception:
                                size_str = "???"

                            desc = ""
                            try:
                                if item.is_relative_to(self.host_os.sandbox_dir):
                                    rel_path = item.relative_to(
                                        self.host_os.sandbox_dir
                                    ).as_posix()
                                    if rel_path in meta:
                                        desc = f" [Description: {meta[rel_path]}]"
                            except Exception:
                                pass

                            lines.append(
                                f"{prefix}{connector}📄 {item.name} ({size_str}){desc}"
                            )
                            lines_count += 1

                except Exception:
                    pass

            root_icon = "🏠" if dir_display == self.host_os.framework_dir.name else "📂"
            lines.append(f"{root_icon} {dir_display}/")

            _build_tree(safe_path, 0, "")

            if lines_count >= limit:
                lines.append(
                    f"└── ... [Лимит вывода {limit} элементов достигнут. Остальные скрыты]"
                )

            if len(lines) == 1:
                lines.append("└── (Пустая директория)")

            system_logger.info(f"[Host OS] Просмотр директории (дерево): {safe_path.name}")
            return SkillResult.ok("\n".join(lines))

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении директории: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def search_files(self, pattern: str, path: str = ".") -> SkillResult:
        """Поиск файлов по маске (например, '*.py', 'log_*.txt') во вложенных папках."""

        limit = self.host_os.config.file_list_limit

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail(
                    "Ошибка: Базовый путь для поиска должен быть директорией."
                )

            meta = self.host_os.get_file_metadata()

            found = []
            for i, file_path in enumerate(safe_path.rglob(pattern)):
                if i >= limit:
                    found.append(f"...[Лимит поиска: найдено более {limit} совпадений] ...")
                    break

                # ПОКАЗЫВАЕМ ПУТЬ ОТ КОРНЯ ПРОЕКТА, ЧТОБЫ АГЕНТ НЕ ПУТАЛСЯ
                try:
                    rel_path = file_path.relative_to(self.host_os.framework_dir).as_posix()
                except ValueError:
                    rel_path = str(file_path)

                try:
                    size_str = (
                        format_size(file_path.stat().st_size) if file_path.is_file() else "DIR"
                    )
                except Exception:
                    size_str = "???"

                desc = ""
                try:
                    if file_path.is_relative_to(self.host_os.sandbox_dir):
                        full_rel_path = file_path.relative_to(
                            self.host_os.sandbox_dir
                        ).as_posix()
                        if full_rel_path in meta:
                            desc = f" [Description: {meta[full_rel_path]}]"
                except Exception:
                    pass

                found.append(f"- {rel_path} ({size_str}){desc}")

            if not found:
                return SkillResult.ok(f"По маске '{pattern}' ничего не найдено.")

            system_logger.info(f"[Host OS] Поиск файлов '{pattern}' в {safe_path.name}")
            return SkillResult.ok("\n".join(found))

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске файлов: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def search_content_in_files(
        self,
        search_string: str,
        path: str = ".",
        case_sensitive: bool = False,
        recursive: bool = True,
    ) -> SkillResult:
        """
        Ищет указанный текст (строку) внутри всех файлов в директории (аналог глобального поиска/grep).
        Возвращает пути к файлам, номера строк и сами строки, где найдено совпадение.
        """

        if not search_string:
            return SkillResult.fail("Строка поиска не может быть пустой.")

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail(f"Ошибка: Путь не является директорией ({path}).")

            # Лимит на количество найденных строк, чтобы не убить контекст агента огромной выдачей
            max_matches = 150

            def _search():
                matches = []
                ignore_dirs = {
                    ".git",
                    "venv",
                    ".venv",
                    "env",
                    "__pycache__",
                    "node_modules",
                    ".pytest_cache",
                }

                iterator = safe_path.rglob("*") if recursive else safe_path.iterdir()
                search_query = search_string if case_sensitive else search_string.lower()

                for item in iterator:
                    if not item.is_file():
                        continue

                    rel_path = item.relative_to(safe_path)

                    # Пропускаем мусорные папки
                    if any(part in ignore_dirs for part in rel_path.parts):
                        continue

                    # Пропускаем бинарники тихо, ловя UnicodeDecodeError
                    try:
                        with open(item, "r", encoding="utf-8") as f:
                            for line_num, line in enumerate(f, 1):
                                check_line = line if case_sensitive else line.lower()

                                if search_query in check_line:
                                    # Форматируем путь: от корня фреймворка (для понятности) или просто имя
                                    try:
                                        display_path = item.relative_to(
                                            self.host_os.framework_dir
                                        ).as_posix()
                                    except ValueError:
                                        display_path = item.name

                                    clean_line = line.strip()
                                    limit = 300
                                    # Ограничим длину выводимой строки (на случай сжатых/минифицированных файлов)
                                    if len(clean_line) > limit:
                                        clean_line = (
                                            clean_line[:limit] + " ... [строка обрезана]"
                                        )

                                    matches.append(
                                        f"- {display_path}:{line_num}: {clean_line}"
                                    )

                                    if len(matches) >= max_matches:
                                        matches.append(
                                            f"\n... [Достигнут лимит в {max_matches} совпадений. Поиск остановлен]"
                                        )
                                        return matches

                    except UnicodeDecodeError:
                        continue  # Бинарный файл - просто идем дальше

                    except Exception:
                        continue  # Проблемы с правами доступа или лок файла

                return matches

            results = await asyncio.to_thread(_search)

            if not results:
                return SkillResult.ok(
                    f"Совпадений по строке '{search_string}' в '{safe_path.name}' не найдено."
                )

            system_logger.info(
                f"[Host OS] Выполнен глобальный поиск текста '{search_string}' в {safe_path.name}"
            )
            return SkillResult.ok(
                f"Результаты поиска '{search_string}':\n" + "\n".join(results)
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске текста: {e}")

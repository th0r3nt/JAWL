import ast
from pathlib import Path
from typing import Literal
import shutil
import asyncio
from typing import Union, List

from src.utils.logger import system_logger
from src.utils._tools import format_size

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents

class HostOSFiles:
    """
    Навыки агента для работы с файловой системой хоста.
    Учитывают уровень доступа (Access Level) через Гейткипер (HostOSClient).
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    # =================================================================================
    # ЧТЕНИЕ ФАЙЛОВ
    # =================================================================================

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def read_file(
        self, filepath: str, read_from: Literal["head", "tail"] = "head"
    ) -> SkillResult:
        """
        Читает содержимое файла. Имеет встроенную защиту от огромных файлов.
        read_from: 'head' (с начала) или 'tail' (с конца, полезно для логов).
        """
        max_chars = self.host_os.config.file_read_max_chars

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(
                    f"Ошибка: Путь не является файлом или не существует ({filepath})."
                )

            def _read_fast():
                with open(safe_path, "rb") as f:
                    f.seek(0, 2)
                    file_size = f.tell()

                    if file_size <= max_chars:
                        f.seek(0)
                        return (
                            f.read().decode("utf-8", errors="replace").replace("\r\n", "\n"),
                            False,
                            file_size,
                        )

                    if read_from == "tail":
                        f.seek(file_size - max_chars)
                        return (
                            f.read().decode("utf-8", errors="replace").replace("\r\n", "\n"),
                            False,
                            file_size,
                        )
                    else:
                        f.seek(0)
                        return (
                            f.read(max_chars).decode("utf-8", errors="replace"),
                            True,
                            file_size,
                        )

            content, is_truncated, file_size = await asyncio.to_thread(_read_fast)

            size_str = format_size(file_size)
            header = f"[Файл: {safe_path.name} | Прочитано: {len(content)} симв. | Исходный размер: {size_str}]\n{'='*40}\n"

            if is_truncated:
                if read_from == "tail":
                    content = f"...[Файл обрезан с начала. Показаны последние {max_chars} байт]...\n{content}"
                else:
                    content = f"{content}\n...[Файл обрезан с конца. Показаны первые {max_chars} байт]..."

            system_logger.info(
                f"[Host OS] Прочитан файл ({read_from}): {safe_path.name} ({size_str})"
            )
            return SkillResult.ok(header + content)

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении файла: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def read_files_in_directory(
        self, path: str = ".", max_files: int = 10, recursive: bool = False
    ) -> SkillResult:
        """
        Читает текстовое содержимое сразу нескольких файлов в директории.
        recursive: Если True, прочитает файлы и во всех вложенных папках.
        Пропускает бинарные файлы.
        """

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail(f"Ошибка: Путь не является директорией ({path}).")

            # Берем лимит из конфига и умножаем на 2, так как файлов много,
            # но в пределах разумного, чтобы не убить контекст агента
            total_max_chars = self.host_os.config.file_read_max_chars * 2

            def _read_all():
                results = []
                total_chars = 0
                files_read = 0

                # Защита: чтобы при recursive=True не сжечь лимит файлов на мусор
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

                for item in iterator:
                    if not item.is_file():
                        continue

                    rel_path = item.relative_to(safe_path)

                    # Пропускаем мусорные папки
                    if recursive and any(part in ignore_dirs for part in rel_path.parts):
                        continue

                    if files_read >= max_files:
                        results.append(
                            f"\n... [Достигнут лимит на чтение {max_files} файлов. Остальные скрыты]"
                        )
                        break

                    try:
                        with open(item, "r", encoding="utf-8") as f:
                            content = f.read()

                        if not content.strip():
                            continue

                        # Считаем остаток квоты
                        chars_left = total_max_chars - total_chars
                        if chars_left <= 0:
                            results.append(
                                "\n... [Достигнут глобальный лимит символов для чтения. Операция прервана]"
                            )
                            break

                        if len(content) > chars_left:
                            content = (
                                content[:chars_left]
                                + "\n... [Файл обрезан из-за системных лимитов]"
                            )

                        total_chars += len(content)

                        # Выводим относительный путь для понимания структуры вложенности
                        results.append(f"--- Файл: {rel_path.as_posix()} ---\n{content}\n")
                        files_read += 1

                    except UnicodeDecodeError:
                        # Пропускаем бинарники тихо
                        continue
                    except Exception as e:
                        results.append(
                            f"--- Файл: {rel_path.as_posix()} ---\n[Ошибка чтения: {e}]\n"
                        )
                        files_read += 1

                return results, files_read, total_chars

            results, files_read, total_chars = await asyncio.to_thread(_read_all)

            if not results:
                return SkillResult.ok(
                    f"Директория '{path}' пуста или содержит только бинарные файлы."
                )

            size_str = format_size(total_chars)
            header = f"[Прочитано файлов: {files_read} из директории {safe_path.name} | Общий объем: {size_str}]\n{'='*60}\n\n"

            system_logger.info(
                f"[Host OS] Массовое чтение {files_read} файлов из директории: {safe_path.name}"
            )
            return SkillResult.ok(header + "\n".join(results))

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при массовом чтении файлов: {e}")

    # =================================================================================
    # РЕДАКТИРОВАНИЕ ФАЙЛОВ
    # =================================================================================

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def write_file(
        self, filepath: str, content: str, description: str = None
    ) -> SkillResult:
        """
        Создает новый файл или полностью перезаписывает существующий.

        Если передан 'description', к файлу сразу будет привязано текстовое описание.
        description: советуется писать полезную информацию. Например, "в файле есть функция X, которая делает Y, принимает на вход аргумент Z и T, возвращает W".

        В будущем это поможет искать нужные функции намного быстрее.
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            def _write():
                with open(safe_path, "w", encoding="utf-8") as f:
                    f.write(content)

            await asyncio.to_thread(_write)

            # Сохраняем описание, если оно передано
            desc_msg = ""
            if description:
                try:
                    rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()
                    clean_desc = description.replace("\n", " ").strip()
                    await asyncio.to_thread(
                        self.host_os.set_file_metadata, rel_path, clean_desc
                    )
                    desc_msg = " Описание файла успешно сохранено."
                except Exception as e:
                    desc_msg = f" (Не удалось сохранить метаданные: {e})"

            size_str = format_size(safe_path.stat().st_size)
            system_logger.info(f"[Host OS] Перезаписан файл: {safe_path.name} ({size_str})")
            return SkillResult.ok(
                f"Файл {safe_path.name} успешно перезаписан. Записано: {len(content)} симв. Размер: {size_str}.{desc_msg}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при перезаписи файла: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def append_to_file(self, filepath: str, content: str) -> SkillResult:
        """
        Безопасно добавляет текст в конец существующего файла.
        Автоматически ставит перенос строки, если его нет.
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            def _append():
                prefix = "\n"
                if safe_path.exists():
                    with open(safe_path, "r", encoding="utf-8") as f:
                        f.seek(0, 2)
                        if f.tell() > 0:
                            f.seek(f.tell() - 1, 0)
                            if f.read(1) == "\n":
                                prefix = ""
                else:
                    prefix = ""

                with open(safe_path, "a", encoding="utf-8") as f:
                    f.write(prefix + content)

            await asyncio.to_thread(_append)

            size_str = format_size(safe_path.stat().st_size)
            system_logger.info(f"[Host OS] Дополнен файл (append): {safe_path.name}")
            return SkillResult.ok(
                f"Текст успешно добавлен в конец файла {safe_path.name}. Размер: {size_str}."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при добавлении в файл: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def delete_lines_matching(
        self, filepath: str, match_string: str, exact_match: bool = False
    ) -> SkillResult:
        """
        Удаляет из файла все строки, которые содержат подстроку 'match_string'.
        Если exact_match=True, строка должна совпадать полностью (без учета пробелов по краям).
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)
            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл не найден ({filepath}).")

            def _delete():
                with open(safe_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                new_lines = []
                deleted_count = 0

                for line in lines:
                    if exact_match:
                        if line.strip() == match_string.strip():
                            deleted_count += 1
                            continue
                    else:
                        if match_string in line:
                            deleted_count += 1
                            continue
                    new_lines.append(line)

                if deleted_count == 0:
                    return False, "Совпадений не найдено. Ни одна строка не удалена."

                with open(safe_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

                return True, f"Успешно удалено строк: {deleted_count}."

            is_success, msg = await asyncio.to_thread(_delete)

            if is_success:
                system_logger.info(f"[Host OS] Удалены строки в файле: {safe_path.name}")
                return SkillResult.ok(msg)
            else:
                return SkillResult.fail(msg)

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении строк: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def patch_file(
        self, filepath: str, search_block: str, replace_block: str
    ) -> SkillResult:
        """
        Точечно заменяет один кусок кода на другой в существующем файле (Search & Replace).
        Важно: search_block должен идеально совпадать с тем, что есть в файле.
        Включая все пробелы, отступы и переносы строк.
        """
        if not search_block:
            return SkillResult.fail("Ошибка: search_block не может быть пустым.")

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)
            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл не найден ({filepath}).")

            def _patch():
                with open(safe_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Сначала пробуем строгое совпадение
                if search_block not in content:
                    # Если строгий поиск не сработал - у LLM часто проблемы с концевыми переносами строк
                    # Делаем умный fallback: чистим \r и ищем без учета пустых строк по краям
                    clean_search = search_block.replace("\r\n", "\n").strip()
                    clean_content = content.replace("\r\n", "\n")

                    if clean_search not in clean_content:
                        return (
                            False,
                            "Блок для поиска (search_block) не найден в файле.",
                        )

                    # Если нашлось в чистом виде - берем замену
                    new_content = clean_content.replace(clean_search, replace_block.strip())
                else:
                    new_content = content.replace(search_block, replace_block)

                with open(safe_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                return True, "Файл успешно пропатчен."

            is_success, msg = await asyncio.to_thread(_patch)

            if is_success:
                system_logger.info(f"[Host OS] Пропатчен файл: {safe_path.name}")
                return SkillResult.ok(msg)
            else:
                return SkillResult.fail(msg)

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при патчинге файла: {e}")

    # =================================================================================
    # РАБОЧАЯ СРЕДА
    # =================================================================================

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def open_file(self, filepath: str) -> SkillResult:
        """
        'Открывает' файл. Содержимое открытого файла всегда будет отображаться в системном промпте (вкладки редактора).
        Крайне полезно и рекомендовано использовать, чтобы держать нужный код перед глазами во время работы над ним.
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
            system_logger.info(f"[Host OS] Файл '{rel_path}' открыт в рабочей среде.")

            return SkillResult.ok(
                f"Файл '{rel_path}' открыт. Теперь его содержимое будет всегда перед глазами."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при открытии файла: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def close_file(self, filepath: str) -> SkillResult:
        """
        'Закрывает' файл, убирая его из системного промпта (вкладок редактора).
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)
            try:
                rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()
            except ValueError:
                rel_path = safe_path.as_posix()

            if rel_path in self.host_os.state.opened_workspace_files:
                self.host_os.state.opened_workspace_files.remove(rel_path)
                system_logger.info(f"[Host OS] Файл '{rel_path}' закрыт.")
                return SkillResult.ok(f"Файл '{rel_path}' закрыт и убран из рабочей среды.")
            else:
                return SkillResult.ok(f"Файл '{rel_path}' и так не был открыт.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при закрытии файла: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def open_directory_workspace(
        self, path: str = ".", recursive: bool = False
    ) -> SkillResult:
        """
        Массово 'открывает' файлы из указанной директории во вкладках редактора.
        recursive: если True, откроет файлы и во всех вложенных подпапках.
        Крайне полезно и рекомендовано, когда нужно держать перед глазами сразу несколько файлов одного модуля.
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
                return SkillResult.ok(msg)

            system_logger.info(
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

    # =================================================================================
    # ОСТАЛЬНЫЕ НАВЫКИ ФАЙЛОВОЙ СИСТЕМЫ
    # =================================================================================

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def list_directory(self, path: str = ".", max_depth: int = 1) -> SkillResult:
        """
        Показывает содержимое директории.
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

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
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

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
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

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def delete_file(self, filepath: str) -> SkillResult:
        """Удаляет указанный файл (не папки)."""

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)

            if not safe_path.exists():
                return SkillResult.fail(f"Ошибка: Файл не существует ({filepath}).")

            if not safe_path.is_file():
                return SkillResult.fail(
                    "Ошибка: Это не файл, удаление директорий через этот инструмент запрещено."
                )

            size_str = format_size(safe_path.stat().st_size)
            safe_path.unlink()

            system_logger.info(f"[Host OS] Удален файл: {safe_path.name} ({size_str})")
            return SkillResult.ok(f"Файл {safe_path.name} ({size_str}) успешно удален.")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении файла: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def delete_directory(self, path: str) -> SkillResult:
        """Удаляет указанную директорию вместе со всем её содержимым."""

        try:
            safe_path = self.host_os.validate_path(path, is_write=True)

            if not safe_path.exists():
                return SkillResult.fail(f"Ошибка: Директория не существует ({path}).")
            if not safe_path.is_dir():
                return SkillResult.fail(
                    "Ошибка: Это не директория. Для удаления файлов используйте delete_file."
                )

            if (
                safe_path == self.host_os.sandbox_dir
                or safe_path == self.host_os.framework_dir
            ):
                return SkillResult.fail(
                    "Ошибка: Отказано в доступе. Запрещено удалять корневую директорию песочницы или фреймворка."
                )

            await asyncio.to_thread(shutil.rmtree, safe_path)
            system_logger.info(f"[Host OS] Удалена директория: {safe_path.name}")
            return SkillResult.ok(
                f"Директория {safe_path.name} и всё её содержимое успешно удалены."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении директории: {e}")

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def create_directories(self, paths: Union[str, List[str]]) -> SkillResult:
        """Создает одну или несколько директорий (папок)."""

        if isinstance(paths, str):
            try:
                parsed = ast.literal_eval(paths.strip())
                if isinstance(parsed, list):
                    paths = parsed
                else:
                    paths = [paths]
            except Exception:
                paths = [paths]

        if not paths or not isinstance(paths, list):
            return SkillResult.fail("Ошибка: Список путей пуст или имеет неверный формат.")

        created, errors = [], []

        for path in paths:
            try:
                safe_path = self.host_os.validate_path(path, is_write=True)
                await asyncio.to_thread(safe_path.mkdir, parents=True, exist_ok=True)
                created.append(safe_path.name)

            except PermissionError as e:
                errors.append(f"{path}: {e}")

            except Exception as e:
                errors.append(f"{path}: Ошибка создания ({e})")

        if not created and errors:
            return SkillResult.fail("Не удалось создать директории:\n" + "\n".join(errors))

        msg = f"Успешно созданы директории: {', '.join(created)}."
        if errors:
            msg += "\n\nНо возникли ошибки с этими путями:\n" + "\n".join(errors)

        system_logger.info(f"[Host OS] Созданы директории: {', '.join(created)}")

        return SkillResult.ok(msg)

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def move_or_rename(self, source_path: str, destination_path: str) -> SkillResult:
        """
        Перемещает/переименовывает файл/директорию.
        Если destination_path указывает на существующую папку, объект будет перемещен внутрь неё.
        """
        try:
            # Проверяем оба пути через гейткипер ОС (и источник, и назначение)
            safe_src = self.host_os.validate_path(source_path, is_write=True)
            safe_dst = self.host_os.validate_path(destination_path, is_write=True)

            if not safe_src.exists():
                return SkillResult.fail(f"Ошибка: Исходный объект не найден ({source_path}).")

            # Создаем родительские папки для назначения, если их нет
            safe_dst.parent.mkdir(parents=True, exist_ok=True)

            def _move():
                shutil.move(str(safe_src), str(safe_dst))

            await asyncio.to_thread(_move)

            system_logger.info(
                f"[Host OS] Перемещен/переименован объект: {safe_src.name} -> {safe_dst.name}"
            )
            return SkillResult.ok(f"Успешно. Объект перемещен по пути: {safe_dst.as_posix()}")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при перемещении/переименовании: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def set_file_description(self, filepath: str, description: str) -> SkillResult:
        """
        Привязывает текстовое описание к любому локальному файлу.
        Полезно для сохранения информации о содержимом картинок, видео, сложных архивов, скриптов или логов,
        чтобы в будущем понимать их суть без повторного чтения/просмотра.
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)
            if not safe_path.exists():
                return SkillResult.fail(f"Ошибка: Файл не найден ({filepath}).")

            rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()
            clean_desc = description.replace("\n", " ").strip()

            await asyncio.to_thread(self.host_os.set_file_metadata, rel_path, clean_desc)

            system_logger.info(f"[Host OS] Добавлено описание для файла: {safe_path.name}")
            return SkillResult.ok(f"Описание успешно привязано к файлу {safe_path.name}.")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при сохранении описания: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def extract_archive(self, archive_path: str, extract_to: str = ".") -> SkillResult:
        """
        Распаковывает архив (zip, tar, gz и др.).
        extract_to: папка, куда будут извлечены файлы (по умолчанию текущая директория).
        """
        try:
            # Проверяем оба пути через гейткипер ОС
            safe_archive = self.host_os.validate_path(archive_path, is_write=False)
            safe_dest = self.host_os.validate_path(extract_to, is_write=True)

            if not safe_archive.is_file():
                return SkillResult.fail(f"Ошибка: Архив не найден ({safe_archive.name}).")

            safe_dest.mkdir(parents=True, exist_ok=True)

            # shutil поддерживает большинство популярных форматов "из коробки"
            await asyncio.to_thread(shutil.unpack_archive, str(safe_archive), str(safe_dest))

            system_logger.info(
                f"[Host OS] Архив {safe_archive.name} распакован в {safe_dest.name}"
            )

            try:
                dest_display = safe_dest.relative_to(self.host_os.sandbox_dir).as_posix()
                dest_msg = f"sandbox/{dest_display}"
            except ValueError:
                dest_msg = safe_dest.as_posix()

            return SkillResult.ok(
                f"Архив {safe_archive.name} успешно распакован в директорию: {dest_msg}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        
        except shutil.ReadError:
            return SkillResult.fail(
                "Ошибка: Неподдерживаемый формат архива или файл поврежден."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка при распаковке архива: {e}")

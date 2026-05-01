"""
Навыки для чтения файлов.
Включает механизмы массового чтения и защиты контекста от переполнения.
"""

import asyncio
from typing import Literal

from src.utils.logger import system_logger
from src.utils._tools import format_size

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class HostOSReader:
    """Навыки агента для безопасного чтения файлов."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def read_file(
        self, filepath: str, read_from: Literal["head", "tail"] = "head"
    ) -> SkillResult:
        """
        Читает содержимое файла. Имеет встроенную защиту от огромных файлов.

        Args:
            read_from: 'head' - с начала, 'tail' - с конца.
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

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def read_files_in_directory(
        self, path: str = ".", max_files: int = 10, recursive: bool = False
    ) -> SkillResult:
        """
        Читает текстовое содержимое сразу нескольких файлов в директории.
        Пропускает бинарные файлы.

        Args:
            recursive: Если True, прочитает файлы и во всех вложенных папках.
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

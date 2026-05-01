"""
Навыки для точечного редактирования (патчинга) файлов.
Экономит токены и снижает риск повреждения большого файла при полной перезаписи.
"""

import asyncio

from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class HostOSEditor:
    """Навыки для точечного редактирования кода."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
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

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def patch_file(
        self, filepath: str, search_block: str, replace_block: str
    ) -> SkillResult:
        """
        Точечная модификация файла.
        Экономит токены и снижает риск повреждения большого файла при полной перезаписи.

        Args:
            filepath: Путь к целевому файлу.
            search_block: Точная копия заменяемого фрагмента (включая отступы и пробелы).
            replace_block: Новый кусок кода, который встанет на место старого.
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

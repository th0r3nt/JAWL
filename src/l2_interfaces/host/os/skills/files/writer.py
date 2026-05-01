"""
Навыки для записи, создания, перемещения и удаления файлов и папок.
"""

import ast
import shutil
import asyncio
from typing import Union, List

from src.utils.logger import system_logger
from src.utils._tools import format_size

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class HostOSWriter:
    """Навыки агента для модификации и управления файловой системой."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def write_file(
        self, filepath: str, content: str, description: str = None
    ) -> SkillResult:
        """
        Создает новый файл или полностью перезаписывает существующий.

        Если передан 'description', к файлу сразу будет привязано текстовое описание.

        Args:
            description: советуется писать полезную информацию. В будущем это поможет искать нужные функции намного быстрее.
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

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
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

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
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

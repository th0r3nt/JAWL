"""
Навыки для работы с архивами.
Включает жесткую защиту от уязвимости ZIP/TAR Slip (выход за пределы директории).
"""

import shutil
import asyncio
import zipfile
import tarfile
from pathlib import Path

from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSArchive:
    """Инструментарий распаковки архивов с проверками безопасности."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    def _is_safe_archive(self, archive_path: Path, extract_to: Path) -> bool:
        """
        Проверяет внутренние пути архива на наличие уязвимости ZIP Slip
        (использование абсолютных путей или '..', пытающихся выйти за пределы extract_to),
        а также на симлинки/хардлинки внутри tar-архивов с таргетом вне песочницы
        (Tar Slip / symlink attack - имя члена выглядит безопасно, но linkname указывает
        на /etc/passwd или другой чувствительный файл, shutil.unpack_archive на Python <3.12
        последует за ним).
        """

        extract_to_resolved = extract_to.resolve()

        def _member_in_sandbox(name: str) -> bool:
            """Резолвит name относительно extract_to и проверяет is_relative_to(sandbox)."""
            member_path = Path(name)
            if member_path.is_absolute():
                return False
            resolved = (extract_to / member_path).resolve()
            return resolved.is_relative_to(extract_to_resolved)

        # Определяем формат архива
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                for name in zf.namelist():
                    if not _member_in_sandbox(name):
                        return False
            return True

        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r") as tf:
                for member in tf.getmembers():
                    # Базовая проверка name: абсолютный / .. / выход из sandbox
                    if not _member_in_sandbox(member.name):
                        return False

                    # Дополнительная проверка для symlink/hardlink: linkname не должен
                    # быть абсолютным и не должен выводить за пределы extract_to.
                    # tf.getnames() эту часть не показывает, поэтому нужны конкретные members.
                    if member.issym() or member.islnk():
                        linkname = member.linkname
                        if not linkname:
                            continue
                        link_path = Path(linkname)
                        if link_path.is_absolute():
                            return False
                        # Резолвим относительно директории, в которой будет лежать сам линк
                        link_parent = (extract_to / Path(member.name)).parent
                        resolved_link = (link_parent / link_path).resolve()
                        if not resolved_link.is_relative_to(extract_to_resolved):
                            return False
            return True

        # Неизвестный формат - делегируем shutil (Python 3.12+ фильтрует опасные члены).
        return True

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def extract_archive(self, archive_path: str, extract_to: str = ".") -> SkillResult:
        """
        Распаковывает архив (zip, tar, gz и др.).

        Args:
            extract_to: папка, куда будут извлечены файлы (по умолчанию текущая директория).
        """
        try:
            # Проверяем оба пути через гейткипер ОС
            safe_archive = self.host_os.validate_path(archive_path, is_write=False)
            safe_dest = self.host_os.validate_path(extract_to, is_write=True)

            if not safe_archive.is_file():
                return SkillResult.fail(f"Ошибка: Архив не найден ({safe_archive.name}).")

            safe_dest.mkdir(parents=True, exist_ok=True)

            # Проверка на ZIP Slip перед распаковкой
            if not await asyncio.to_thread(self._is_safe_archive, safe_archive, safe_dest):
                system_logger.warning(
                    f"[Security] Заблокирована распаковка {safe_archive.name}: обнаружена уязвимость ZIP Slip."
                )
                return SkillResult.fail(
                    "Ошибка безопасности: Обнаружена попытка выхода за пределы директории "
                    "внутри архива (ZIP Slip). Распаковка заблокирована."
                )

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

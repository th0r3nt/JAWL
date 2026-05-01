"""
Навыки для привязки описаний и метаданных к локальным файлам.
"""

import asyncio

from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSMetadata:
    """Управление метаданными файлов (описания)."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

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

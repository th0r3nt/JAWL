import os
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest

from src.utils.logger import system_logger

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill


class TelethonAccount:
    """
    Навыки для управления профилем (имя, био, аватар).
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    @skill()
    async def change_username(self, name: str, surname: str = "") -> SkillResult:
        """Меняет имя и (опционально) фамилию профиля."""
        try:
            client = self.tg_client.client()

            # В Telegram "name" - это first_name, а "surname" - last_name
            await client(UpdateProfileRequest(first_name=name, last_name=surname))

            system_logger.info(f"Имя Telegram профиля изменено: {name} {surname}")
            return SkillResult.ok(f"Имя профиля успешно изменено на '{name} {surname}'.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении имени: {e}")

    @skill()
    async def change_bio(self, text: str) -> SkillResult:
        """Изменяет описание (био) профиля. Макс. длина - 70 символов."""
        try:
            client = self.tg_client.client()

            await client(UpdateProfileRequest(about=text))

            system_logger.info(f"Био ТГ профиля изменено на: {text}")
            return SkillResult.ok("Биография успешно изменена.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении био: {e}")

    @skill()
    async def change_avatar(self, filepath: str) -> SkillResult:
        """Изменяет аватар профиля."""
        if not os.path.exists(filepath):
            return SkillResult.fail(f"Ошибка: Файл для аватара не найден ({filepath}).")

        try:
            client = self.tg_client.client()

            # Сначала загружаем файл на сервера Telegram
            uploaded_file = await client.upload_file(filepath)

            # Затем устанавливаем загруженный файл как фото профиля
            await client(UploadProfilePhotoRequest(file=uploaded_file))

            system_logger.info(f"Аватар Telegram профиля обновлен файлом: {filepath}")
            return SkillResult.ok("Аватар профиля успешно изменен.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении аватара: {e}")

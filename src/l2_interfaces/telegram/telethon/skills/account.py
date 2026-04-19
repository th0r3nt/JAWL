import os
from typing import Union

from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.functions.contacts import AddContactRequest

# from src.utils.logger import system_logger

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill


class TelethonAccount:
    """
    Навыки для управления профилем (имя, био, аватар) и списком контактов.
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    def _parse_entity(self, entity_id: Union[int, str]) -> Union[int, str]:
        """Утилитный метод для преобразования строковых ID в числа."""
        try:
            return int(entity_id)
        except ValueError:
            return str(entity_id).strip()

    @skill()
    async def change_username(self, name: str, surname: str = "") -> SkillResult:
        """Меняет имя и (опционально) фамилию профиля."""
        try:
            client = self.tg_client.client()

            # В Telegram "name" - это first_name, а "surname" - last_name
            await client(UpdateProfileRequest(first_name=name, last_name=surname))

            # Обновляем стейт, чтобы контекст агента сразу актуализировался
            await self.tg_client.update_profile_state()

            # system_logger.info(f"[Telegram Telethon] Имя профиля изменено: {name} {surname}")
            return SkillResult.ok(f"Имя профиля успешно изменено на '{name} {surname}'.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении имени: {e}")

    @skill()
    async def change_bio(self, text: str) -> SkillResult:
        """Изменяет описание (био) профиля. Макс. длина - 70 символов."""
        try:
            client = self.tg_client.client()

            await client(UpdateProfileRequest(about=text))

            # Обновляем стейт
            await self.tg_client.update_profile_state()

            # system_logger.info(f"[Telegram Telethon] Био профиля изменено на: {text}")
            return SkillResult.ok("[Telegram Telethon] Биография успешно изменена.")

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

            # system_logger.info(
            #     f"[Telegram Telethon] Аватар профиля обновлен файлом: {filepath}"
            # )
            return SkillResult.ok("Аватар профиля успешно изменен.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении аватара: {e}")

    @skill()
    async def add_contact(
        self, user_id: Union[int, str], first_name: str, last_name: str = ""
    ) -> SkillResult:
        """Добавляет пользователя в контакты Telegram."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(self._parse_entity(user_id))

            # Telethon позволяет добавить контакт без номера телефона,
            # передав пустую строку и InputUser объект
            await client(
                AddContactRequest(
                    id=target_entity,
                    first_name=first_name,
                    last_name=last_name,
                    phone="",
                    add_phone_privacy_exception=False,
                )
            )

            name_str = f"{first_name} {last_name}".strip()
            # system_logger.info(
            #     f"[Telegram Telethon] Пользователь {user_id} добавлен в контакты как '{name_str}'"
            # )
            return SkillResult.ok(
                f"Успешно. Пользователь {user_id} добавлен в контакты как '{name_str}'."
            )

        except ValueError:
            return SkillResult.fail(
                f"Ошибка: Пользователь '{user_id}' не найден. Проверьте правильность ID или юзернейма."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка при добавлении в контакты: {e}")

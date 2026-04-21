from typing import Union

from telethon.tl.functions.account import UpdateProfileRequest, UpdatePersonalChannelRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.functions.contacts import AddContactRequest
from telethon.tl.functions.users import GetFullUserRequest

from src.utils.logger import system_logger
from src.utils._tools import format_size, validate_sandbox_path, parse_int_or_str

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill


class TelethonAccount:
    """
    Навыки для управления профилем (имя, био, аватар) и списком контактов.
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    @skill()
    async def change_username(self, name: str, surname: str = "") -> SkillResult:
        """Меняет имя и (опционально) фамилию профиля агента."""
        try:
            client = self.tg_client.client()

            # В Telegram "name" - это first_name, а "surname" - last_name
            await client(UpdateProfileRequest(first_name=name, last_name=surname))

            # Обновляем стейт, чтобы контекст агента сразу актуализировался
            await self.tg_client.update_profile_state()

            return SkillResult.ok(f"Имя профиля успешно изменено на '{name} {surname}'.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении имени: {e}")

    @skill()
    async def change_bio(self, text: str) -> SkillResult:
        """Изменяет описание (био) профиля агента. Макс. длина - 70 символов."""
        try:
            client = self.tg_client.client()
            await client(UpdateProfileRequest(about=text))
            await self.tg_client.update_profile_state()

            return SkillResult.ok("[Telegram Telethon] Биография успешно изменена.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении био: {e}")

    @skill()
    async def change_avatar(self, filepath: str) -> SkillResult:
        """Изменяет аватар профиля агента. Файл должен быть в sandbox/."""
        try:
            safe_path = validate_sandbox_path(filepath)

            if not safe_path.exists():
                return SkillResult.fail(
                    f"Ошибка: Файл для аватара не найден ({safe_path.name})."
                )

            client = self.tg_client.client()
            uploaded_file = await client.upload_file(str(safe_path))
            await client(UploadProfilePhotoRequest(file=uploaded_file))

            return SkillResult.ok("Аватар профиля успешно изменен.")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении аватара: {e}")

    @skill()
    async def add_contact(
        self, user_id: Union[int, str], first_name: str, last_name: str = ""
    ) -> SkillResult:
        """Добавляет пользователя в контакты Telegram."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(parse_int_or_str(user_id))

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
            return SkillResult.ok(
                f"Успешно. Пользователь {user_id} добавлен в контакты как '{name_str}'."
            )

        except ValueError:
            return SkillResult.fail(
                f"Ошибка: Пользователь '{user_id}' не найден. Проверьте ID или юзернейм."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка при добавлении в контакты: {e}")

    @skill()
    async def download_avatar(
        self, user_or_chat_id: Union[int, str], dest_filename: str, avatar_index: int = 0
    ) -> SkillResult:
        """
        Скачивает аватар (фото профиля) пользователя, канала или группы в папку sandbox/.
        avatar_index: 0 - текущий аватар, 1 - предыдущий и т.д. (если доступна история фото).
        """
        try:
            safe_path = validate_sandbox_path(dest_filename)
            client = self.tg_client.client()
            entity = await client.get_entity(parse_int_or_str(user_or_chat_id))

            # Запрашиваем историю фотографий (до нужного нам индекса)
            photos = await client.get_profile_photos(entity, limit=avatar_index + 1)

            if not photos or avatar_index >= len(photos):
                count = len(photos) if photos else 0
                return SkillResult.fail(
                    f"Ошибка: Аватар с индексом {avatar_index} не найден. Всего доступно аватаров: {count}."
                )

            target_photo = photos[avatar_index]

            system_logger.info(
                f"[Telegram Telethon] Скачивание аватара (индекс {avatar_index})..."
            )
            downloaded_path = await client.download_media(target_photo, file=str(safe_path))

            if not downloaded_path:
                return SkillResult.fail("Не удалось скачать аватар (возможно нет доступа).")

            size_str = format_size(safe_path.stat().st_size)
            system_logger.info(
                f"[Telegram Telethon] Аватар скачан: {safe_path.name} ({size_str})"
            )

            return SkillResult.ok(
                f"Аватар успешно скачан и сохранен как: sandbox/{safe_path.name} ({size_str})"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except ValueError:
            return SkillResult.fail("Ошибка: Пользователь или чат не найден.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при скачивании аватара: {e}")

    @skill()
    async def get_user_info(self, user_id: Union[int, str]) -> SkillResult:
        """Получает подробную информацию о конкретном пользователе (имя, био, статус)."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(parse_int_or_str(user_id))

            full_user = await client(GetFullUserRequest(target_entity))
            user = full_user.users[0]

            lines = [f"Информация о пользователе {user_id}:"]
            lines.append(f"Имя: {user.first_name or ''} {user.last_name or ''}".strip())

            if user.username:
                lines.append(f"Юзернейм: @{user.username}")

            if full_user.full_user.about:
                lines.append(f"О себе (Bio): {full_user.full_user.about}")

            if user.bot:
                lines.append("Статус: Бот")

            if user.restricted:
                lines.append(
                    "[Внимание: На аккаунт наложены ограничения Telegram (Restricted)]"
                )

            if user.scam or user.fake:
                lines.append("[Внимание: Аккаунт помечен как SCAM или FAKE]")

            return SkillResult.ok("\n".join(lines))

        except ValueError:
            return SkillResult.fail(
                "Ошибка: Пользователь не найден. Рекомендуется проверить ID или юзернейм."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении информации о пользователе: {e}")

    @skill()
    async def set_personal_channel(self, channel_id: Union[int, str]) -> SkillResult:
        """
        Устанавливает указанный канал как личный (будет отображаться в профиле).
        Для удаления канала из профиля - передать пустую строку "".
        """
        try:
            client = self.tg_client.client()

            # Обрабатываем удаление канала
            if not channel_id or str(channel_id).strip() == "":
                target_entity = None
            else:
                target_entity = await client.get_input_entity(parse_int_or_str(channel_id))

            # Отправляем запрос на обновление профиля
            await client(UpdatePersonalChannelRequest(channel=target_entity))

            # Актуализируем стейт агента, чтобы он сразу "осознал", что профиль обновился
            await self.tg_client.update_profile_state()

            if target_entity:
                return SkillResult.ok(f"Успешно. Канал '{channel_id}' установлен как личный.")
            else:
                return SkillResult.ok("Успешно. Личный канал убран из профиля.")

        except ValueError:
            return SkillResult.fail(
                f"Ошибка: Канал '{channel_id}' не найден. Проверьте ID или юзернейм."
            )
        except Exception as e:
            if "CHANNEL_PRIVATE" in str(e):
                return SkillResult.fail(
                    "Ошибка: Канал приватный, либо у агента нет к нему доступа."
                )
            return SkillResult.fail(f"Ошибка при установке личного канала: {e}")

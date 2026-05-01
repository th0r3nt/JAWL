"""
Навыки управления собственным профилем агента (Telethon).

Позволяют агенту менять имя, биографию, аватарку, добавлять людей в контакты
и просматривать детальную информацию о чужих профилях (в том числе сетевой статус).
"""

from typing import Union

from telethon.tl.functions.account import UpdateProfileRequest, UpdatePersonalChannelRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.functions.contacts import AddContactRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import (
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
)

from src.utils.dtime import format_datetime
from src.utils.logger import system_logger
from src.utils._tools import format_size, validate_sandbox_path, parse_int_or_str

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill


class TelethonAccount:
    """Группа навыков для управления профилем и контактами."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def change_username(self, name: str, surname: str = "") -> SkillResult:
        """
        Меняет публичное имя и (опционально) фамилию профиля агента.

        Args:
            name (str): Новое имя (first_name).
            surname (str, optional): Новая фамилия (last_name).
        """
        try:
            client = self.tg_client.client()

            await client(UpdateProfileRequest(first_name=name, last_name=surname))

            # Обновляем стейт, чтобы контекст агента сразу актуализировался
            await self.tg_client.update_profile_state()

            return SkillResult.ok(f"Имя профиля успешно изменено на '{name} {surname}'.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении имени: {e}")

    @skill()
    async def change_bio(self, text: str) -> SkillResult:
        """
        Изменяет описание (биографию/о себе) профиля агента.
        Максимальная длина - 70 символов.

        Args:
            text (str): Текст биографии.
        """
        try:
            client = self.tg_client.client()
            await client(UpdateProfileRequest(about=text))
            await self.tg_client.update_profile_state()

            return SkillResult.ok("Биография успешно изменена.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении био: {e}")

    @skill()
    async def change_avatar(self, filepath: str) -> SkillResult:
        """
        Устанавливает новую аватарку профиля агента.

        Args:
            filepath (str): Относительный путь к картинке внутри папки sandbox/.
        """
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
        """
        Добавляет пользователя в системную записную книжку (контакты) Telegram.

        Args:
            user_id (Union[int, str]): ID пользователя или его юзернейм (@username).
            first_name (str): Имя для сохранения.
            last_name (str, optional): Фамилия.
        """
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
        Скачивает текущую (или одну из предыдущих) фотографий пользователя, группы или канала.
        Сохраняет файл в песочницу (sandbox/download/).

        Args:
            user_or_chat_id (Union[int, str]): Идентификатор пользователя или чата.
            dest_filename (str): Имя файла для сохранения локально.
            avatar_index (int, optional): Индекс фото. 0 - текущее, 1 - предыдущее и т.д.
        """
        try:
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"download/{dest_filename}"

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
        """
        Возвращает детальную информацию о конкретном пользователе Telegram
        (имя, био, сетевой статус, наличие premium/scam/bot флагов).

        Args:
            user_id (Union[int, str]): ID или юзернейм пользователя.
        """
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

            # Парсинг сетевого статуса
            status_str = "Неизвестно (или скрыто настройками приватности)"
            if isinstance(user.status, UserStatusOnline):
                status_str = "В сети (Online)"
            elif isinstance(user.status, UserStatusOffline):
                dt_str = format_datetime(user.status.was_online, self.tg_client.timezone)
                status_str = f"Был(а) в сети: {dt_str}"
            elif isinstance(user.status, UserStatusRecently):
                status_str = "Был(а) недавно"
            elif isinstance(user.status, UserStatusLastWeek):
                status_str = "Был(а) на этой неделе"
            elif isinstance(user.status, UserStatusLastMonth):
                status_str = "Был(а) в этом месяце"

            lines.append(f"Сетевой статус: {status_str}")

            if user.bot:
                lines.append("Статус аккаунта: Бот")
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
        Устанавливает указанный канал как личный (будет отображаться в био профиля).
        Для удаления личного канала из профиля необходимо передать пустую строку "".

        Args:
            channel_id (Union[int, str]): ID или юзернейм канала.
        """
        try:
            client = self.tg_client.client()

            # Обрабатываем удаление канала
            if not channel_id or str(channel_id).strip() == "":
                target_entity = None
            else:
                target_entity = await client.get_input_entity(parse_int_or_str(channel_id))

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
                    "Ошибка: Канал приватный, либо у вас нет к нему доступа."
                )
            return SkillResult.fail(f"Ошибка при установке личного канала: {e}")

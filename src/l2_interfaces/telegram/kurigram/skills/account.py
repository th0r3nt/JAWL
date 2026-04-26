from typing import Union

from pyrogram import raw

from src.utils.dtime import format_datetime, format_timestamp
from src.utils.logger import system_logger
from src.utils._tools import format_size, validate_sandbox_path, parse_int_or_str

from src.l2_interfaces.telegram.kurigram.client import KurigramClient
from src.l3_agent.skills.registry import SkillResult, skill


class KurigramAccount:
    """
    Навыки для управления профилем (имя, био, аватар) и списком контактов.
    """

    def __init__(self, tg_client: KurigramClient):
        self.tg_client = tg_client

    @staticmethod
    def _normalize_peer_id(peer_id: Union[int, str]) -> Union[int, str]:
        parsed = parse_int_or_str(peer_id)
        if isinstance(parsed, str):
            return parsed.strip().lstrip("@")
        return parsed

    @staticmethod
    async def _resolve_input_user(client, user_id: Union[int, str]):
        peer = await client.resolve_peer(KurigramAccount._normalize_peer_id(user_id))

        if isinstance(peer, raw.types.InputPeerSelf):
            return raw.types.InputUserSelf()

        if isinstance(peer, raw.types.InputPeerUser):
            return raw.types.InputUser(
                user_id=peer.user_id,
                access_hash=peer.access_hash,
            )

        raise ValueError("Target peer is not a user.")

    @staticmethod
    async def _resolve_input_channel(client, channel_id: Union[int, str]):
        peer = await client.resolve_peer(KurigramAccount._normalize_peer_id(channel_id))

        if isinstance(peer, raw.types.InputPeerChannel):
            return raw.types.InputChannel(
                channel_id=peer.channel_id,
                access_hash=peer.access_hash,
            )

        raise ValueError("Target peer is not a channel.")

    @staticmethod
    def _format_raw_user_status(status, timezone: int) -> str:
        status_str = "Неизвестно (или скрыто настройками приватности)"

        if isinstance(status, raw.types.UserStatusOnline):
            return "В сети (Online)"

        if isinstance(status, raw.types.UserStatusOffline):
            was_online = status.was_online
            if isinstance(was_online, (int, float)):
                dt_str = format_timestamp(was_online, timezone)
            else:
                dt_str = format_datetime(was_online, timezone)
            return f"Был(а) в сети: {dt_str}"

        if isinstance(status, raw.types.UserStatusRecently):
            return "Был(а) недавно"

        if isinstance(status, raw.types.UserStatusLastWeek):
            return "Был(а) на этой неделе"

        if isinstance(status, raw.types.UserStatusLastMonth):
            return "Был(а) в этом месяце"

        return status_str

    @skill()
    async def change_username(self, name: str, surname: str = "") -> SkillResult:
        """Меняет имя и (опционально) фамилию профиля агента."""
        try:
            client = self.tg_client.client()

            # В Telegram "name" - это first_name, а "surname" - last_name
            await client.update_profile(first_name=name, last_name=surname)

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
            await client.update_profile(bio=text)
            await self.tg_client.update_profile_state()

            return SkillResult.ok("[Telegram Kurigram] Биография успешно изменена.")

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
            await client.set_profile_photo(photo=str(safe_path))

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
            await client.add_contact(
                user_id=self._normalize_peer_id(user_id),
                first_name=first_name,
                last_name=last_name,
                phone_number="",
                share_phone_number=False,
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
        Скачивает аватар (фото профиля) пользователя, канала или группы. По умолчанию в sandbox/download/.
        avatar_index: 0 - текущий аватар, 1 - предыдущий и т.д. (если доступна история фото).
        """
        try:
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"download/{dest_filename}"

            safe_path = validate_sandbox_path(dest_filename)
            client = self.tg_client.client()

            # Запрашиваем историю фотографий (до нужного нам индекса)
            photos = []
            async for photo in client.get_chat_photos(
                self._normalize_peer_id(user_or_chat_id),
                limit=avatar_index + 1,
            ):
                photos.append(photo)

            if not photos or avatar_index >= len(photos):
                count = len(photos) if photos else 0
                return SkillResult.fail(
                    f"Ошибка: Аватар с индексом {avatar_index} не найден. Всего доступно аватаров: {count}."
                )

            target_photo = photos[avatar_index]

            system_logger.info(
                f"[Telegram Kurigram] Скачивание аватара (индекс {avatar_index})..."
            )
            downloaded_path = await client.download_media(
                target_photo,
                file_name=str(safe_path),
            )

            if not downloaded_path:
                return SkillResult.fail("Не удалось скачать аватар (возможно нет доступа).")

            size_str = format_size(safe_path.stat().st_size)
            system_logger.info(
                f"[Telegram Kurigram] Аватар скачан: {safe_path.name} ({size_str})"
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
        """Получает подробную информацию о конкретном пользователе (имя, био, статус в сети)."""
        try:
            client = self.tg_client.client()
            target_user = self._normalize_peer_id(user_id)
            target_input_user = await self._resolve_input_user(client, target_user)

            full_user = await client.invoke(
                raw.functions.users.GetFullUser(id=target_input_user)
            )
            user = full_user.users[0] if full_user.users else None

            if not user:
                return SkillResult.fail(
                    "Ошибка: Пользователь не найден. Рекомендуется проверить ID или юзернейм."
                )

            lines = [f"Информация о пользователе {user_id}:"]
            lines.append(f"Имя: {user.first_name or ''} {user.last_name or ''}".strip())

            if user.username:
                lines.append(f"Юзернейм: @{user.username}")

            if full_user.full_user.about:
                lines.append(f"О себе (Bio): {full_user.full_user.about}")

            status_str = self._format_raw_user_status(
                getattr(user, "status", None),
                self.tg_client.timezone,
            )

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
        Устанавливает указанный канал как личный (будет отображаться в профиле).
        Для удаления канала из профиля - передать пустую строку "".
        """
        try:
            client = self.tg_client.client()

            # Обрабатываем удаление канала
            if not channel_id or str(channel_id).strip() == "":
                target_channel = raw.types.InputChannelEmpty()
            else:
                target_channel = await self._resolve_input_channel(client, channel_id)

            # Отправляем запрос на обновление профиля
            await client.invoke(
                raw.functions.account.UpdatePersonalChannel(channel=target_channel)
            )

            # Актуализируем стейт агента, чтобы он сразу "осознал", что профиль обновился
            await self.tg_client.update_profile_state()

            if not isinstance(target_channel, raw.types.InputChannelEmpty):
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

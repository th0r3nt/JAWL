from inspect import Parameter, signature
from typing import Union

from src.utils._tools import validate_sandbox_path, parse_int_or_str
from src.utils.logger import system_logger
from src.l2_interfaces.telegram.kurigram.client import KurigramClient
from src.l3_agent.skills.registry import SkillResult, skill


class KurigramAdmin:
    """
    Навыки администратора: создание каналов, управление участниками, закрепление сообщений и выдача прав.
    """

    def __init__(self, tg_client: KurigramClient):
        self.tg_client = tg_client

    @staticmethod
    def _chat_administrator_rights(**kwargs):
        try:
            from pyrogram.types import ChatAdministratorRights
        except ImportError:
            from pyrogram.types import ChatPrivileges as ChatAdministratorRights

        parameters = signature(ChatAdministratorRights).parameters.values()
        if not any(param.kind == Parameter.VAR_KEYWORD for param in parameters):
            allowed_kwargs = {param.name for param in parameters}
            kwargs = {key: value for key, value in kwargs.items() if key in allowed_kwargs}

        return ChatAdministratorRights(**kwargs)


    @skill()
    async def create_channel(
        self, title: str, about: str = "", is_megagroup: bool = False
    ) -> SkillResult:
        """
        Создает новый приватный канал (или супергруппу).
        is_megagroup: Если True, будет создана группа для общения. Если False - канал (только для публикаций).
        """

        try:
            client = self.tg_client.client()
            result = (
                await client.create_supergroup(title=title, description=about)
                if is_megagroup
                else await client.create_channel(title=title, description=about)
            )

            chat_id = getattr(result, "id", "Unknown")
            chat_type = "Супергруппа" if is_megagroup else "Канал"

            msg = f"{chat_type} '{title}' успешно создан. ID: {chat_id}"
            system_logger.info(f"[Telegram Kurigram] {msg}")
            return SkillResult.ok(msg)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании чата: {e}")

    @skill()
    async def set_channel_username(
        self, chat_id: Union[int, str], username: str
    ) -> SkillResult:
        """
        Устанавливает публичный юзернейм (ссылку) для канала или супергруппы.
        Чтобы сделать канал снова приватным - передать пустую строку в username ("").
        """

        try:
            client = self.tg_client.client()
            clean_username = username.strip().lstrip("@")

            await client.set_chat_username(parse_int_or_str(chat_id), clean_username)

            if clean_username:
                system_logger.info(
                    f"[Telegram Kurigram] Канал {chat_id} стал публичным (@{clean_username})"
                )
                return SkillResult.ok(
                    f"Успешно. Канал теперь публичный: t.me/{clean_username}"
                )
            else:
                system_logger.info(f"[Telegram Kurigram] Канал {chat_id} стал приватным")
                return SkillResult.ok("Успешно. Юзернейм удален, канал стал приватным.")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении статуса канала: {e}")

    @skill()
    async def set_discussion_group(
        self, channel_id: Union[int, str], group_id: Union[int, str]
    ) -> SkillResult:
        """
        Привязывает супергруппу (is_megagroup=True) к каналу в качестве группы для обсуждений (комментариев).
        Нужны права администратора для обоих групп. Чтобы отвязать группу - передать пустую строку "" в group_id.
        """
        try:
            client = self.tg_client.client()
            channel_entity = parse_int_or_str(channel_id)

            unlink_group = not group_id or str(group_id).strip() == ""

            if unlink_group:
                group_entity = None
            else:
                group_entity = parse_int_or_str(group_id)

            await client.set_chat_discussion_group(
                chat_id=channel_entity,
                discussion_chat_id=group_entity,
            )

            action_str = "отвязана от канала" if unlink_group else "привязана к каналу"
            msg = f"Супергруппа успешно {action_str} {channel_id}."
            system_logger.info(f"[Telegram Kurigram] {msg}")

            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID канала или группы.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при привязке группы обсуждений: {e}")

    @skill()
    async def edit_chat_title(self, chat_id: Union[int, str], new_title: str) -> SkillResult:
        """Меняет название группы или канала."""

        try:
            client = self.tg_client.client()
            await client.set_chat_title(parse_int_or_str(chat_id), new_title)

            system_logger.info(
                f"[Telegram Kurigram] Название чата {chat_id} изменено на '{new_title}'"
            )
            return SkillResult.ok(f"Название чата успешно изменено на '{new_title}'.")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении названия чата: {e}")

    @skill()
    async def edit_chat_description(
        self, chat_id: Union[int, str], new_description: str
    ) -> SkillResult:
        """Изменяет описание (about/bio) группы или канала. Требуются права администратора."""
        try:
            client = self.tg_client.client()
            await client.set_chat_description(parse_int_or_str(chat_id), new_description)

            system_logger.info(
                f"[Telegram Kurigram] Описание чата {chat_id} успешно изменено."
            )
            return SkillResult.ok("Описание чата успешно изменено.")
        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении описания чата: {e}")

    @skill()
    async def edit_chat_avatar(self, chat_id: Union[int, str], filepath: str) -> SkillResult:
        """Изменяет аватар группы или канала. Файл должен лежать в sandbox/."""
        try:
            safe_path = validate_sandbox_path(filepath)
            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл {safe_path.name} не найден.")

            client = self.tg_client.client()
            await client.set_chat_photo(parse_int_or_str(chat_id), photo=str(safe_path))

            system_logger.info(
                f"[Telegram Kurigram] Аватар чата {chat_id} изменен на {safe_path.name}"
            )
            return SkillResult.ok("Аватар чата успешно изменен.")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении аватара чата: {e}")

    @skill()
    async def create_invite_link(self, chat_id: Union[int, str]) -> SkillResult:
        """Генерирует новую пригласительную ссылку для указанного чата."""

        try:
            client = self.tg_client.client()
            result = await client.export_chat_invite_link(parse_int_or_str(chat_id))

            link = getattr(result, "invite_link", result)
            return SkillResult.ok(f"Пригласительная ссылка сгенерирована: {link}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при генерации ссылки: {e}")

    @skill()
    async def get_participants(
        self, chat_id: Union[int, str], limit: int = 100
    ) -> SkillResult:
        """Возвращает список участников группы или канала."""

        try:
            client = self.tg_client.client()

            participants = []
            async for member in client.get_chat_members(parse_int_or_str(chat_id), limit=limit):
                user = member.user
                if not user:
                    continue
                name = " ".join(
                    part
                    for part in (getattr(user, "first_name", ""), getattr(user, "last_name", ""))
                    if part
                ) or getattr(user, "username", None) or "Unknown"
                bot_tag = " [Bot]" if getattr(user, "is_bot", False) else ""
                participants.append(f"- ID: `{user.id}` | Имя: {name}{bot_tag}")

            if not participants:
                return SkillResult.ok("Список участников пуст (или нет прав на его просмотр).")

            return SkillResult.ok(
                f"Участники (последние {limit} чел.):\n" + "\n".join(participants)
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении участников: {e}")

    @skill()
    async def promote_user(
        self, chat_id: Union[int, str], user_id: Union[int, str], add_admins: bool = False
    ) -> SkillResult:
        """
        Выдает пользователю права администратора в чате.
        Если add_admins=True, пользователь сможет назначать других администраторов.
        """

        try:
            client = self.tg_client.client()

            await client.promote_chat_member(
                chat_id=parse_int_or_str(chat_id),
                user_id=parse_int_or_str(user_id),
                privileges=self._chat_administrator_rights(
                    can_manage_chat=True,
                    can_change_info=True,
                    can_post_messages=True,
                    can_edit_messages=True,
                    can_delete_messages=True,
                    can_restrict_members=True,
                    can_invite_users=True,
                    can_pin_messages=True,
                    can_promote_members=add_admins,
                    can_manage_topics=True,
                ),
            )

            return SkillResult.ok(f"Пользователь {user_id} успешно повышен до администратора.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при выдаче прав администратора: {e}")

    @skill()
    async def demote_user(
        self, chat_id: Union[int, str], user_id: Union[int, str]
    ) -> SkillResult:
        """Забирает у пользователя права администратора (понижает до обычного участника)."""

        try:
            client = self.tg_client.client()

            await client.promote_chat_member(
                chat_id=parse_int_or_str(chat_id),
                user_id=parse_int_or_str(user_id),
                privileges=self._chat_administrator_rights(
                    can_manage_chat=False,
                    can_change_info=False,
                    can_post_messages=False,
                    can_edit_messages=False,
                    can_delete_messages=False,
                    can_restrict_members=False,
                    can_invite_users=False,
                    can_pin_messages=False,
                    can_promote_members=False,
                    can_manage_topics=False,
                ),
            )

            return SkillResult.ok(f"Пользователь {user_id} понижен до обычного участника.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при снятии прав администратора: {e}")

    @skill()
    async def pin_message(
        self, chat_id: Union[int, str], message_id: int, notify: bool = True
    ) -> SkillResult:
        """Закрепляет сообщение в группе или канале. notify=True (с уведомлением всех), False (тихо)."""

        try:
            client = self.tg_client.client()
            await client.pin_chat_message(
                parse_int_or_str(chat_id),
                int(message_id),
                disable_notification=not notify,
            )

            system_logger.info(
                f"[Telegram Kurigram] Сообщение {message_id} закреплено в {chat_id}"
            )
            return SkillResult.ok(f"Сообщение {message_id} успешно закреплено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при закреплении сообщения: {e}")

    @skill()
    async def unpin_message(self, chat_id: Union[int, str], message_id: int) -> SkillResult:
        """Открепляет конкретное сообщение в чате."""

        try:
            client = self.tg_client.client()
            await client.unpin_chat_message(parse_int_or_str(chat_id), int(message_id))

            system_logger.info(
                f"[Telegram Kurigram] Сообщение {message_id} откреплено в {chat_id}"
            )
            return SkillResult.ok(f"Сообщение {message_id} успешно откреплено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при откреплении сообщения: {e}")

    @skill()
    async def create_topic(self, chat_id: Union[int, str], title: str) -> SkillResult:
        """
        Создает новый топик (раздел) в группе с включенными темами (Форуме).
        Возвращает ID созданного топика (его нужно использовать как topic_id для отправки сообщений туда).
        """
        try:
            client = self.tg_client.client()
            result = await client.create_forum_topic(parse_int_or_str(chat_id), title)

            topic_id = getattr(result, "id", None) or getattr(result, "message_thread_id", None)
            if not topic_id:
                return SkillResult.fail("Топик создан, но не удалось извлечь его ID.")

            msg = f"Топик '{title}' успешно создан. ID топика: {topic_id}"
            system_logger.info(f"[Telegram Kurigram] {msg} (чат {chat_id})")
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            if "CHAT_NOT_MODIFIED" in str(e) or "not a forum" in str(e).lower():
                return SkillResult.fail(
                    "Ошибка: Этот чат не является форумом (в нем не включены темы)."
                )
            return SkillResult.fail(f"Ошибка при создании топика: {e}")

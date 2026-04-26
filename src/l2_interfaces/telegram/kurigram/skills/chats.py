from typing import Any, Optional, Union

from pyrogram import raw

from src.utils.dtime import format_datetime
from src.utils.logger import system_logger
from src.utils._tools import parse_int_or_str

from src.l3_agent.skills.registry import SkillResult, skill


class KurigramChats:
    """
    Навыки для работы со списком чатов, чтения сообщений и управления участием.
    """

    def __init__(self, tg_client: Any):
        self.tg_client = tg_client

    # =================================================================
    # Навыки
    # =================================================================

    @skill()
    async def get_chats(self, limit: int = 10) -> SkillResult:
        """
        Возвращает список последних чатов (пользователи, группы, каналы).
        Если это форум, возвращает топики.
        """

        try:
            client = self.tg_client.client()
            chats = []

            total_dialogs = 0
            try:
                total_dialogs = await client.get_dialogs_count()
            except Exception:
                pass

            async for dialog in client.get_dialogs(limit=limit):
                chat = dialog.chat
                chat_type = self._chat_type(chat)
                unread_count = self._dialog_unread_count(dialog)
                unread = f" [UNREAD: {unread_count}]" if unread_count > 0 else ""

                forum_str = ""
                if self._is_forum_chat(chat, dialog):
                    chat_type = "Forum"
                    topics_list = []
                    try:
                        topics_data = await self._get_topics(client, chat, limit=10)
                        for topic in topics_data:
                            topic_unread = getattr(topic, "unread_count", 0) or 0
                            t_unread = (
                                f" (UNREAD: {topic_unread})" if topic_unread > 0 else ""
                            )
                            topics_list.append(
                                f"      ↳ Топик '{getattr(topic, 'title', 'Unknown')}' (ID: {topic.id}){t_unread}"
                            )
                    except Exception as e:
                        system_logger.error(
                            f"[Telegram Kurigram] Ошибка при получении топиков в get_chats: {e}"
                        )

                    if not topics_list and unread_count > 0:
                        topics_list.append(
                            f"      ↳ General / Общий топик (UNREAD: {unread_count})"
                        )

                    if topics_list:
                        forum_str = "\n" + "\n".join(topics_list)

                chats.append(
                    f"- {chat_type} | ID: `{chat.id}` | Название: {self._chat_name(chat)}{unread}{forum_str}"
                )

            if not chats:
                return SkillResult.ok("Список чатов пуст.")

            res_str = "\n".join(chats)

            if total_dialogs > len(chats):
                hidden = total_dialogs - len(chats)
                res_str += (
                    f"\n\n...и еще {hidden} чатов скрыто. Для просмотра - увеличить "
                    "параметр limit, чтобы загрузить больше."
                )

            return SkillResult.ok(res_str)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка чатов: {e}")

    @skill()
    async def get_unread_chats(self, limit: int = 20) -> SkillResult:
        """
        Возвращает список чатов, в которых есть непрочитанные сообщения.
        """
        try:
            client = self.tg_client.client()
            chats = []

            async for dialog in client.get_dialogs(limit=limit):
                unread_count = self._dialog_unread_count(dialog)
                if unread_count > 0:
                    chat = dialog.chat
                    chat_type = self._chat_type(chat)
                    forum_str = ""

                    if self._is_forum_chat(chat, dialog):
                        chat_type = "Forum"
                        topics_list = []
                        try:
                            topics_data = await self._get_topics(client, chat, limit=100)
                            for topic in topics_data:
                                unread = getattr(topic, "unread_count", 0) or 0
                                if unread > 0:
                                    title = getattr(topic, "title", "Unknown")
                                    topics_list.append(
                                        f"      ↳ Топик '{title}' (ID: {topic.id}) "
                                        f"[UNREAD: {unread}]"
                                    )
                        except Exception as e:
                            system_logger.error(
                                f"[Telegram Kurigram] Ошибка при получении топиков в get_unread_chats: {e}"
                            )

                        if not topics_list:
                            topics_list.append(
                                f"      ↳ General / Другие топики [UNREAD: {unread_count}]"
                            )

                        forum_str = "\n" + "\n".join(topics_list)

                    chat_name = self._chat_name(chat)
                    chats.append(
                        f"- {chat_type} | ID: `{chat.id}` | Название: **{chat_name}** "
                        f"| UNREAD: {unread_count}{forum_str}"
                    )

            if not chats:
                return SkillResult.ok("Нет непрочитанных сообщений.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске непрочитанных чатов: {e}")

    @skill()
    async def read_chat(
        self, chat_id: Union[int, str], limit: int = 10, topic_id: Optional[int] = None
    ) -> SkillResult:
        """
        Читает историю указанного чата (не помечая сообщения прочитанными).
        """
        try:
            client = self.tg_client.client()
            target = parse_int_or_str(chat_id)
            target_chat = await client.get_chat(target)

            read_outbox_max_id = await self._read_outbox_max_id(client, target)

            messages = []
            if topic_id:
                iterator = client.get_discussion_replies(
                    target, int(topic_id), limit=limit
                )
            else:
                iterator = client.get_chat_history(target, limit=limit)

            async for msg in iterator:
                formatted = await self._build_message_string(
                    client=client,
                    target_chat=target_chat,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    topic_id=topic_id,
                    read_outbox_max_id=read_outbox_max_id,
                )
                messages.append(formatted)

            draft_text = await self._get_draft_text(client, target_chat.id, topic_id)

            if not messages:
                base_msg = (
                    "В этом топике нет сообщений."
                    if topic_id
                    else "В этом чате нет сообщений."
                )
                return SkillResult.ok(base_msg + draft_text)

            messages.reverse()
            return SkillResult.ok("\n\n".join(messages) + draft_text)

        except ValueError:
            return SkillResult.fail(f"Ошибка: Некорректный ID чата ({chat_id}).")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении чата {chat_id}: {e}")

    @skill()
    async def mark_as_read(
        self, chat_id: Union[int, str], topic_id: Optional[int] = None
    ) -> SkillResult:
        """Помечает все сообщения в чате (или конкретном топике) как прочитанные."""
        try:
            client = self.tg_client.client()
            target = parse_int_or_str(chat_id)
            target_chat = await client.get_chat(target)

            if self._is_forum_chat(target_chat) and not topic_id:
                try:
                    topics_data = await self._get_topics(client, target_chat, limit=100)
                    for topic in topics_data:
                        if (getattr(topic, "unread_count", 0) or 0) > 0:
                            await self._mark_chat_read(client, target, topic.id)

                except Exception as e:
                    system_logger.error(f"[Telegram Kurigram] Ошибка при очистке топиков: {e}")

                await self._mark_chat_read(client, target)
            else:
                await self._mark_chat_read(client, target, topic_id)

            return SkillResult.ok(f"Чат {chat_id} успешно помечен как прочитанный.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при пометке чата {chat_id} как прочитанного: {e}")

    @skill()
    async def search_public_chats(self, query: str, limit: int = 5) -> SkillResult:
        """Ищет публичные группы и каналы в глобальном поиске Telegram по запросу."""

        try:
            client = self.tg_client.client()
            result = await client.invoke(
                raw.functions.contacts.Search(q=query, limit=limit)
            )

            chats = []
            for chat in getattr(result, "chats", []):
                chat_type = "Channel" if getattr(chat, "broadcast", False) else "Group"
                username = f"@{chat.username}" if getattr(chat, "username", None) else "Нет"

                participants = getattr(chat, "participants_count", None)
                part_str = (
                    f" | Подписчиков: {participants}" if participants is not None else ""
                )

                chats.append(
                    f"- {chat_type} | ID: `{chat.id}` | Название: "
                    f"{getattr(chat, 'title', 'Unknown')} | Юзернейм: "
                    f"{username}{part_str}"
                )

            if not chats:
                return SkillResult.ok(f"По глобальному запросу '{query}' ничего не найдено.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске чатов: {e}")

    @skill()
    async def get_chat_info(self, chat_id: Union[int, str]) -> SkillResult:
        """
        Получает информацию о конкретном чате (описание, кол-во участников/подписчиков).
        Можно передавать ID чата или юзернейм (@username).
        """

        try:
            client = self.tg_client.client()
            chat = await client.get_chat(parse_int_or_str(chat_id))

            lines = [f"Информация о чате {chat_id}:"]
            lines.append(f"Название: {self._chat_name(chat)}")

            if getattr(chat, "username", None):
                lines.append(f"Юзернейм: @{chat.username}")

            lines.append(f"Тип: {self._chat_type(chat)}")

            description = getattr(chat, "description", None) or getattr(chat, "bio", None)
            if description:
                lines.append(f"Описание: {description}")

            members_count = (
                getattr(chat, "members_count", None)
                or getattr(chat, "participants_count", None)
            )
            if members_count is not None:
                if self._chat_type(chat) == "Channel":
                    lines.append(f"Участников (подписчиков): {members_count}")
                else:
                    lines.append(f"Участников: {members_count}")

            linked_chat = getattr(chat, "linked_chat", None)
            if linked_chat:
                lines.append(
                    f"Группа обсуждений: {self._chat_name(linked_chat)} (ID: {linked_chat.id})"
                )

            return SkillResult.ok("\n".join(lines))

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата или юзернейм.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении информации о чате: {e}")

    @skill()
    async def join_chat(self, link_or_username: str) -> SkillResult:
        """Вступает в канал или группу по юзернейму или ссылке."""
        target = link_or_username.strip()
        try:
            client = self.tg_client.client()
            await client.join_chat(target)

            return SkillResult.ok(f"Успешно вступили в чат: {target}")

        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                return SkillResult.ok(f"Вы уже состоите в этом чате ({target}).")

            return SkillResult.fail(f"Ошибка при вступлении в чат: {e}")

    @skill()
    async def leave_chat(self, chat_id: Union[int, str]) -> SkillResult:
        """Покидает канал или группу."""

        try:
            client = self.tg_client.client()
            await client.leave_chat(parse_int_or_str(chat_id))

            return SkillResult.ok(f"Успешно покинули чат {chat_id}.")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный формат ID чата.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при выходе из чата: {e}")

    @skill()
    async def join_channel_discussion(self, channel_id: Union[int, str]) -> SkillResult:
        """Узнает ID привязанной группы для комментариев у канала и вступает в нее."""
        try:
            client = self.tg_client.client()
            channel = await client.get_chat(parse_int_or_str(channel_id))

            linked_chat = getattr(channel, "linked_chat", None)
            linked_chat_id = getattr(linked_chat, "id", None)

            if not linked_chat_id:
                input_channel = await self._resolve_input_channel(
                    client, parse_int_or_str(channel_id)
                )
                full_channel = await client.invoke(
                    raw.functions.channels.GetFullChannel(channel=input_channel)
                )
                linked_chat_id = getattr(full_channel.full_chat, "linked_chat_id", None)
                linked_chat_id = self._pyrogram_chat_id(linked_chat_id)

            if not linked_chat_id:
                return SkillResult.fail(
                    f"Ошибка: У канала {channel_id} нет привязанной группы для обсуждений."
                )

            await client.join_chat(linked_chat_id)

            return SkillResult.ok(
                f"Успешное вступление в группу обсуждений (ID: {linked_chat_id})."
            )

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID канала.")
        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                return SkillResult.ok("Вы уже состоите в группе обсуждений этого канала.")
            return SkillResult.fail(f"Ошибка при вступлении в обсуждение: {e}")

    @skill()
    async def invite_to_chat(
        self, chat_id: Union[int, str], users: list[Union[int, str]]
    ) -> SkillResult:
        """
        Приглашает одного или нескольких пользователей в группу или канал.
        users: Список из числовых ID или юзернеймов (@username).
        """
        if not users:
            return SkillResult.fail("Ошибка: Список пользователей пуст.")

        try:
            client = self.tg_client.client()
            target_chat = parse_int_or_str(chat_id)
            user_ids = [parse_int_or_str(user) for user in users]

            await client.add_chat_members(target_chat, user_ids, forward_limit=0)

            return SkillResult.ok(f"Успешно. Пользователи {users} приглашены в чат {chat_id}.")

        except ValueError as e:
            return SkillResult.fail(f"Ошибка: Некорректный ID или юзернейм: {e}")

        except Exception as e:
            msg = str(e)

            if "USER_PRIVACY_RESTRICTED" in msg:
                return SkillResult.fail(
                    "Ошибка: Настройки приватности ограничивают добавление кого-то из списка."
                )

            if "CHAT_ADMIN_REQUIRED" in msg:
                return SkillResult.fail("Ошибка: Нет прав на приглашение в этот чат.")

            if "USER_ALREADY_PARTICIPANT" in msg:
                return SkillResult.ok(
                    "Запрос выполнен, некоторые (или все) пользователи уже состоят в чате."
                )

            if "USER_NOT_MUTUAL_CONTACT" in msg:
                return SkillResult.fail(
                    "Ошибка: Пользователя можно пригласить только если вы взаимные контакты."
                )

            return SkillResult.fail(f"Ошибка при инвайтинге: {e}")

    # ===============================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # ===============================================================

    async def _get_topics(self, client: Any, chat: Any, limit: int = 100) -> list:
        """Хелпер: получает список топиков форума через Raw API Pyrogram/Kurigram."""
        target = getattr(chat, "id", chat)

        get_forum_topics = getattr(client, "get_forum_topics", None)
        if callable(get_forum_topics):
            try:
                topics = []
                async for topic in get_forum_topics(target, limit=limit):
                    topics.append(topic)
                return topics
            except Exception as e:
                system_logger.debug(
                    f"[Telegram Kurigram] get_forum_topics недоступен, fallback на raw API: {e}"
                )

        try:
            peer = await client.resolve_peer(target)
            result = await client.invoke(
                raw.functions.messages.GetForumTopics(
                    peer=peer,
                    q="",
                    offset_date=0,
                    offset_id=0,
                    offset_topic=0,
                    limit=limit,
                )
            )
            return getattr(result, "topics", [])
        except Exception as e:
            system_logger.error(f"[Telegram Kurigram] Ошибка _get_topics: {e}")
            return []

    async def _mark_chat_read(
        self, client: Any, chat_id: Union[int, str], topic_id: Optional[int] = None
    ):
        """Хелпер: Помечает сообщения, меншны и реакции прочитанными."""

        try:
            peer = await client.resolve_peer(chat_id)

            if topic_id:
                latest_topic_message_id = await self._latest_topic_message_id(
                    client, chat_id, int(topic_id)
                )
                await client.invoke(
                    raw.functions.messages.ReadDiscussion(
                        peer=peer,
                        msg_id=int(topic_id),
                        read_max_id=latest_topic_message_id,
                    )
                )
            else:
                await client.read_chat_history(chat_id)

            kwargs = {"peer": peer}
            if topic_id:
                kwargs["top_msg_id"] = int(topic_id)

            await client.invoke(raw.functions.messages.ReadMentions(**kwargs))
            await client.invoke(raw.functions.messages.ReadReactions(**kwargs))

        except Exception as e:
            system_logger.debug(f"[Telegram Kurigram] Ошибка при очистке реакций/меншнов: {e}")

    async def _latest_topic_message_id(
        self, client: Any, chat_id: Union[int, str], topic_id: int
    ) -> int:
        try:
            async for message in client.get_discussion_replies(
                chat_id, topic_id, limit=1
            ):
                return getattr(message, "id", topic_id) or topic_id
        except Exception:
            pass
        return topic_id

    async def _read_outbox_max_id(self, client: Any, chat_id: Union[int, str]) -> int:
        try:
            peer = await client.resolve_peer(chat_id)
            peer_dialogs = await client.invoke(
                raw.functions.messages.GetPeerDialogs(
                    peers=[raw.types.InputDialogPeer(peer=peer)]
                )
            )
            if peer_dialogs and peer_dialogs.dialogs:
                return getattr(peer_dialogs.dialogs[0], "read_outbox_max_id", 0) or 0
        except Exception:
            pass
        return 0

    async def _get_draft_text(
        self, client: Any, target_chat_id: int, topic_id: Optional[int]
    ) -> str:
        try:
            drafts = await client.invoke(raw.functions.messages.GetAllDrafts())
            target_peer = await client.resolve_peer(target_chat_id)
            target_key = self._peer_key(target_peer)

            for update in getattr(drafts, "updates", []):
                if self._peer_key(getattr(update, "peer", None)) != target_key:
                    continue

                update_topic_id = self._topic_id(getattr(update, "top_msg_id", None))
                if topic_id and update_topic_id != int(topic_id):
                    continue
                if not topic_id and update_topic_id:
                    continue

                draft = getattr(update, "draft", None)
                text = getattr(draft, "message", None) or getattr(draft, "text", None)
                if text:
                    return f"\n\n[Черновик (Неотправленное сообщение)]:\n{text}"
                return ""
        except Exception as e:
            system_logger.debug(f"[Telegram Kurigram] Ошибка raw-получения черновика: {e}")

        try:
            async for dialog in client.get_dialogs():
                if getattr(dialog.chat, "id", None) != target_chat_id:
                    continue

                draft = getattr(dialog, "draft", None)
                if not draft:
                    return ""

                if topic_id:
                    draft_topic_id = (
                        getattr(draft, "reply_to_top_message_id", None)
                        or getattr(draft, "reply_to_message_id", None)
                    )
                    if draft_topic_id != int(topic_id):
                        return ""

                text = getattr(draft, "text", None) or getattr(draft, "message", None)
                if text:
                    return f"\n\n[Черновик (Неотправленное сообщение)]:\n{text}"
                return ""
        except Exception as e:
            system_logger.debug(f"[Telegram Kurigram] Ошибка при получении черновика: {e}")
        return ""

    async def _resolve_input_channel(self, client: Any, chat_id: Union[int, str]) -> Any:
        peer = await client.resolve_peer(chat_id)
        if hasattr(peer, "channel_id"):
            return raw.types.InputChannel(
                channel_id=peer.channel_id, access_hash=peer.access_hash
            )
        return peer

    @staticmethod
    def _peer_key(peer: Any) -> tuple[str, int] | None:
        for attr in ("user_id", "chat_id", "channel_id"):
            value = getattr(peer, attr, None)
            if value is not None:
                return attr, int(value)
        return None

    @staticmethod
    def _topic_id(value: Any) -> Optional[int]:
        return value if isinstance(value, int) else None

    @staticmethod
    def _dialog_unread_count(dialog: Any) -> int:
        return (
            getattr(dialog, "unread_messages_count", None)
            or getattr(dialog, "unread_count", None)
            or 0
        )

    @staticmethod
    def _is_forum_chat(chat: Any, dialog: Any = None) -> bool:
        return bool(
            getattr(chat, "is_forum", False)
            or getattr(chat, "forum", False)
            or (dialog and getattr(dialog, "view_as_topics", False))
        )

    @staticmethod
    def _chat_type(chat: Any) -> str:
        raw_type = getattr(chat, "type", None)
        type_value = getattr(raw_type, "value", raw_type)
        type_value = str(type_value).lower() if type_value else ""

        if type_value in {"private", "bot"}:
            return "User"
        if type_value == "channel":
            return "Channel"
        if type_value in {"group", "supergroup"}:
            return "Group"
        return "Channel" if getattr(chat, "is_channel", False) else "Group"

    @staticmethod
    def _chat_name(chat: Any) -> str:
        title = getattr(chat, "title", None)
        if title:
            return title

        first_name = getattr(chat, "first_name", "") or ""
        last_name = getattr(chat, "last_name", "") or ""
        name = f"{first_name} {last_name}".strip()
        if name:
            return name

        username = getattr(chat, "username", None)
        return f"@{username}" if username else "Unknown"

    @staticmethod
    def _pyrogram_chat_id(raw_chat_id: Any) -> Any:
        if not isinstance(raw_chat_id, int) or raw_chat_id <= 0:
            return raw_chat_id
        return int(f"-100{raw_chat_id}")

    async def _build_message_string(
        self,
        client: Any,
        target_chat: Any,
        msg: Any,
        timezone: int,
        topic_id: Optional[int] = None,
        read_outbox_max_id: int = 0,
    ) -> str:
        read_status = ""
        if getattr(msg, "outgoing", False):
            read_status = (
                " [Прочитано]"
                if getattr(msg, "id", 0) <= read_outbox_max_id
                else " [Не прочитано]"
            )

        sender_name = self._sender_name(msg)
        reply_info = await self._reply_info(client, target_chat.id, msg, topic_id)

        parts = [
            self._media_tag(msg),
            getattr(msg, "text", None) or getattr(msg, "caption", None) or "",
            self._forward_info(msg),
            reply_info,
            self._reactions_info(msg),
            self._buttons_info(msg),
        ]

        final_text = " ".join(filter(bool, parts)) or "[Пустое сообщение]"
        time_str = format_datetime(msg.date, timezone, fmt="%Y-%m-%d %H:%M")

        topic_str = ""
        if not topic_id:
            message_thread_id = (
                getattr(msg, "message_thread_id", None)
                or getattr(msg, "reply_to_top_message_id", None)
            )
            if message_thread_id:
                topic_str = f" [Topic: {message_thread_id}]"

        return (
            f"[{time_str}] [ID: {msg.id}]{topic_str}{read_status} {sender_name}: {final_text}"
        )

    def _sender_name(self, msg: Any) -> str:
        sender = getattr(msg, "from_user", None)
        if sender:
            name = self._user_name(sender)
            return f"{name} (ID: {sender.id})" if getattr(sender, "id", None) else name

        sender_chat = getattr(msg, "sender_chat", None)
        if sender_chat:
            return self._chat_name(sender_chat)

        chat = getattr(msg, "chat", None)
        if chat:
            return self._chat_name(chat)

        return "Unknown"

    @staticmethod
    def _user_name(user: Any) -> str:
        first_name = getattr(user, "first_name", "") or ""
        last_name = getattr(user, "last_name", "") or ""
        name = f"{first_name} {last_name}".strip()
        if name:
            return name

        username = getattr(user, "username", None)
        if username:
            return f"@{username}"

        return "Deleted Account" if getattr(user, "is_deleted", False) else "Anonymous"

    @staticmethod
    def _media_tag(msg: Any) -> str:
        if getattr(msg, "service", None):
            return "[Системное сообщение]"

        if getattr(msg, "photo", None):
            return "[Фотография]"
        if getattr(msg, "sticker", None):
            emoji = getattr(msg.sticker, "emoji", "") or ""
            return f"[Стикер {emoji}]" if emoji else "[Стикер]"
        if getattr(msg, "animation", None):
            return "[GIF]"
        if getattr(msg, "voice", None):
            return "[Голосовое сообщение]"
        if getattr(msg, "video", None) or getattr(msg, "video_note", None):
            return "[Видео]"
        if getattr(msg, "document", None):
            return "[Файл]"
        if getattr(msg, "poll", None):
            return "[Опрос]"
        if getattr(msg, "media", None):
            return "[Медиа]"
        return ""

    @staticmethod
    def _instance_attr(obj: Any, name: str, default: Any = None) -> Any:
        if obj is None:
            return default
        value = vars(obj).get(name, default)
        return default if type(value).__module__.startswith("unittest.mock") else value

    def _forward_info(self, msg: Any) -> str:
        forward_origin = getattr(msg, "forward_origin", None)
        if forward_origin:
            user = getattr(forward_origin, "sender_user", None)
            chat = getattr(forward_origin, "chat", None) or getattr(
                forward_origin, "sender_chat", None
            )
            sender_name = getattr(forward_origin, "sender_user_name", None)
            if user:
                return f"\n  ↳[Переслано от: {self._user_name(user)}]"
            if chat:
                return f"\n  ↳[Переслано от: {self._chat_name(chat)}]"
            if sender_name:
                return f"\n  ↳[Переслано от: {sender_name}]"
            return "\n  ↳[Переслано]"

        forward_from = self._instance_attr(msg, "forward_from")
        if forward_from:
            return f"\n  ↳[Переслано от: {self._user_name(forward_from)}]"

        forward_from_chat = self._instance_attr(msg, "forward_from_chat")
        if forward_from_chat:
            return f"\n  ↳[Переслано от: {self._chat_name(forward_from_chat)}]"

        forward_sender_name = self._instance_attr(msg, "forward_sender_name")
        if forward_sender_name:
            return f"\n  ↳[Переслано от: {forward_sender_name}]"

        return ""

    async def _reply_info(
        self, client: Any, chat_id: Union[int, str], msg: Any, topic_id: Optional[int]
    ) -> str:
        reply_id = getattr(msg, "reply_to_message_id", None)
        top_id = getattr(msg, "reply_to_top_message_id", None)

        if not reply_id or str(reply_id) == str(topic_id) or reply_id == top_id:
            return ""

        try:
            orig_msg = await client.get_messages(chat_id, reply_id)
            if orig_msg:
                sender = self._sender_name(orig_msg)
                return f"\n  ↳ (В ответ на сообщение ID {reply_id} от {sender})"
        except Exception:
            pass

        return f"\n  ↳ (В ответ на сообщение ID {reply_id})"

    @staticmethod
    def _reactions_info(msg: Any) -> str:
        reactions = getattr(msg, "reactions", None)
        if not reactions:
            return ""

        r_list = []
        raw_reactions = (
            getattr(reactions, "reactions", None)
            or getattr(reactions, "results", None)
            or []
        )

        for reaction in raw_reactions:
            emoji = (
                getattr(reaction, "emoji", None)
                or getattr(getattr(reaction, "reaction", None), "emoticon", None)
                or "[CustomEmoji]"
            )
            count = getattr(reaction, "count", None)
            r_list.append(f"{emoji} x{count}" if count is not None else str(emoji))

        return f"\n  ↳[Реакции: {', '.join(r_list)}]" if r_list else ""

    @staticmethod
    def _buttons_info(msg: Any) -> str:
        reply_markup = getattr(msg, "reply_markup", None)
        if not reply_markup:
            return ""

        rows = getattr(reply_markup, "inline_keyboard", None) or []
        btn_texts = [
            f"[{button.text}]"
            for row in rows
            for button in row
            if getattr(button, "text", None)
        ]
        return f"\n  ↳[Кнопки: {', '.join(btn_texts)}]" if btn_texts else ""

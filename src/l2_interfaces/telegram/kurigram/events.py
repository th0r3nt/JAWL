from __future__ import annotations

import re
import time
from datetime import datetime
from inspect import isawaitable
from typing import Any

from pyrogram import filters, raw, utils as pyrogram_utils
from pyrogram.handlers import MessageHandler, RawUpdateHandler
from pyrogram.types import Chat, Message, User
from pyrogram.errors import FloodWait

from src.utils._tools import truncate_text
from src.utils.dtime import format_datetime
from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.state import KurigramState


class KurigramEvents:
    _MISSING = object()

    def __init__(
        self,
        tg_client: Any,
        state: KurigramState,
        event_bus: EventBus,
    ):
        self.tg_client = tg_client
        self.state = state
        self.bus = event_bus
        self._last_state_update = 0.0
        self._handlers: list[tuple[Any, int]] = []
        self._me: User | None = None

        # Кэш описаний чатов (чтобы не убить API Telegram'а лимитами)
        self._chat_desc_cache: dict[int, str] = {}

    async def start(self) -> None:
        client = self.tg_client.client()
        if self._handlers:
            await self.stop()

        await self._ensure_me()
        await self._update_state(force=True)

        self._add_handler(
            client,
            MessageHandler(
                self._on_private_message,
                filters.private & filters.incoming & ~filters.service,
            ),
        )
        self._add_handler(
            client,
            MessageHandler(
                self._on_group_message,
                filters.group & filters.incoming & ~filters.service,
            ),
        )
        self._add_handler(
            client,
            MessageHandler(
                self._on_channel_message,
                filters.channel & filters.incoming & ~filters.service,
            ),
        )
        self._add_handler(
            client,
            MessageHandler(self._on_chat_action, filters.service & filters.incoming),
        )
        self._add_handler(client, RawUpdateHandler(self._on_reaction))

        # Слушаем исходящие сообщения
        self._add_handler(
            client,
            MessageHandler(self._on_outgoing_message, filters.outgoing & ~filters.service),
        )

        system_logger.info("[Telegram Kurigram] Слушатели событий успешно запущены.")

    async def stop(self) -> None:
        client = self.tg_client.client()
        for handler, group in reversed(self._handlers):
            try:
                client.remove_handler(handler, group)
            except Exception as e:
                system_logger.warning(f"[Telegram Kurigram] Не удалось снять handler: {e}")
        self._handlers.clear()
        system_logger.info("[Telegram Kurigram] Слушатели событий успешно остановлены.")

    @staticmethod
    def _is_mock_value(value: Any) -> bool:
        return type(value).__module__.startswith("unittest.mock")

    @classmethod
    def _get(cls, obj: Any, *names: str, default: Any = None) -> Any:
        if obj is None:
            return default

        for name in names:
            value = getattr(obj, name, cls._MISSING)
            if value is not cls._MISSING and not cls._is_mock_value(value):
                return value

        return default

    @classmethod
    def _instance_attr(cls, obj: Any, name: str, default: Any = None) -> Any:
        if obj is None:
            return default
        value = vars(obj).get(name, default)
        return default if cls._is_mock_value(value) else value

    @classmethod
    def _clean_text(cls, value: Any) -> str:
        if value is None or cls._is_mock_value(value):
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
        return str(value).strip()

    @classmethod
    def _int_or_none(cls, value: Any) -> int | None:
        if value is None or cls._is_mock_value(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    async def _maybe_await(cls, value: Any) -> Any:
        if isawaitable(value):
            return await value
        return value

    def _add_handler(self, client: Any, handler: Any, group: int = 0) -> None:
        client.add_handler(handler, group=group)
        self._handlers.append((handler, group))

    async def _ensure_me(self) -> User | None:
        if self._me:
            return self._me

        try:
            self._me = await self.tg_client.client().get_me()
        except Exception:
            self._me = None
        return self._me

    async def _update_state(self, force: bool = False):
        """Обновляет состояние (последние n чатов и профиль агента)."""
        now = time.time()

        if not force and now - self._last_state_update < 3:
            return

        self._last_state_update = now

        client = self.tg_client.client()
        chats = []

        try:
            async for dialog in client.get_dialogs(limit=self.state.number_of_last_chats):
                chat = self._get(dialog, "chat")
                if not chat:
                    continue

                chat_id = self._chat_id(chat)

                if (
                    self._is_group_chat(chat) or self._is_channel_chat(chat)
                ) and chat_id not in self._chat_desc_cache:
                    self._chat_desc_cache[chat_id] = await self._load_chat_description(
                        client, chat
                    )

                desc = self._chat_desc_cache.get(chat_id, "")
                if desc:
                    clean_desc = desc.replace("\n", " ")
                    desc_str = (
                        f" | Описание: {truncate_text(clean_desc, 100, '... [Обрезано]')}"
                    )
                else:
                    desc_str = ""

                is_public = bool(self._get(chat, "username"))
                status_str = "Public" if is_public else "Private"

                participants = (
                    self._get(chat, "members_count")
                    or self._get(chat, "participants_count")
                )
                part_str = f" | {participants} чел." if participants else ""

                unread_count = (
                    self._int_or_none(self._get(dialog, "unread_messages_count"))
                    or self._int_or_none(self._get(dialog, "unread_count"))
                    or 0
                )
                unread = f" [UNREAD: {unread_count}]" if unread_count > 0 else ""
                chat_name = self._display_name(chat)

                if self._is_private_chat(chat):
                    bot_tag = " [Bot]" if self._get(chat, "is_bot", default=False) else ""
                    chats.append(f"[User] {chat_name}{bot_tag} (ID: {chat_id}){unread}")

                    limit = self.state.private_chat_history_limit
                    if limit > 0:
                        try:
                            recent_msgs = await self._get_chat_history(
                                client, chat_id, limit=limit
                            )
                            if recent_msgs:
                                chats.append(f"    Last {limit} messages:")
                                for msg in self._history_to_chronological(recent_msgs):
                                    formatted = await self._build_message_string(
                                        client=client,
                                        chat_id=chat_id,
                                        msg=msg,
                                        truncate_text_flag=True,
                                    )
                                    indented = "\n".join(
                                        [f"        {line}" for line in formatted.split("\n")]
                                    )
                                    chats.append(indented)
                        except Exception:
                            chats.append("    [Ошибка загрузки истории]")

                elif self._is_group_chat(chat):
                    chats.append(
                        f"[{status_str} Group] {chat_name} (ID: {chat_id}){part_str}{desc_str}{unread}"
                    )
                elif self._is_channel_chat(chat):
                    chats.append(
                        f"[{status_str} Channel] {chat_name} (ID: {chat_id}){part_str}{desc_str}{unread}"
                    )

            if not chats:
                self.state.last_chats = "Список диалогов пуст."
            else:
                self.state.last_chats = "\n".join(chats)

        except Exception as e:
            system_logger.error(f"[Telegram Kurigram] Ошибка обновления стейта: {e}")

    # ==========================================================
    # ЭВЕНТЫ
    # ==========================================================

    async def _on_outgoing_message(self, _client: Any, _message: Message):
        """Триггер на исходящие сообщения (агент ответил, либо юзер написал с телефона)."""
        # Форсируем обновление стейта, чтобы агент на следующем шаге ReAct видел свой же ответ
        await self._update_state(force=True)

    async def _on_private_message(self, client: Any, message: Message) -> None:
        await self._update_state(force=True)

        chat = self._get(message, "chat")
        chat_name = self._display_name(chat) if chat else "Unknown"
        chat_id = self._message_chat_id(message)

        msg_id = self._message_id(message)
        enriched_message = await self._enriched_message(client, message, chat_id)
        history = await self._fetch_recent_history(
            chat_id, limit=5, current_msg_id=msg_id
        )

        payload = {
            "message": enriched_message,
            "sender_name": await self._sender_name(message),
            "chat_name": chat_name,
            "chat_id": chat_id,
            "msg_id": msg_id,
        }
        if history:
            payload["recent_history"] = history

        await self.bus.publish(Events.KURIGRAM_MESSAGE_INCOMING, **payload)

    async def _on_group_message(self, client: Any, message: Message):
        mentioned = await self._is_mentioned(message)
        event_type = (
            Events.KURIGRAM_GROUP_MENTION
            if mentioned
            else Events.KURIGRAM_GROUP_MESSAGE
        )

        await self._update_state(force=True)

        chat = self._get(message, "chat")
        chat_name = self._display_name(chat) if chat else "Unknown"
        chat_id = self._message_chat_id(message)
        topic_id, topic_name = await self._topic_info(client, message, chat_id)

        msg_id = self._message_id(message)
        enriched_message = await self._enriched_message(
            client, message, chat_id, topic_id=topic_id
        )

        payload = {
            "message": enriched_message,
            "sender_name": await self._sender_name(message),
            "chat_name": chat_name,
            "chat_id": chat_id,
            "msg_id": msg_id,
        }

        if topic_id:
            payload["topic_id"] = topic_id
            if topic_name:
                payload["topic_name"] = topic_name

        if mentioned:
            history = await self._fetch_recent_history(
                chat_id, limit=10, current_msg_id=msg_id
            )
            if history:
                payload["recent_history"] = history

        await self.bus.publish(event_type, **payload)

    async def _on_reaction(self, _client: Any, update: Any, *_args: Any) -> None:
        reaction_update = getattr(raw.types, "UpdateMessageReactions", None)
        if reaction_update is not None and isinstance(update, reaction_update):
            is_reaction_update = True
        else:
            class_name = update.__class__.__name__ if update is not None else ""
            is_reaction_update = (
                class_name == "UpdateMessageReactions"
                or (
                    self._get(update, "peer") is not None
                    and self._get(update, "msg_id") is not None
                    and self._get(update, "reactions") is not None
                )
            )

        if not is_reaction_update:
            return

        await self._update_state()

        chat_id = self._peer_id(self._get(update, "peer"))

        reactions_str = "Реакции удалены"
        reactions = self._get(update, "reactions")
        reaction_values = (
            self._get(reactions, "results")
            or self._get(reactions, "reactions")
            or self._get(reactions, "recent_reactions")
            if reactions
            else None
        )
        if reaction_values:
            r_list = []
            for result in reaction_values:
                emo = self._reaction_label(result)
                count = self._int_or_none(self._get(result, "count"))
                r_list.append(f"{emo} x{count}" if count is not None else emo)

            if r_list:
                reactions_str = ", ".join(r_list)

        await self.bus.publish(
            Events.KURIGRAM_MESSAGE_REACTION,
            chat_id=chat_id,
            message_id=self._get(update, "msg_id"),
            reactions=reactions_str,
        )

    async def _on_channel_message(self, client: Any, message: Message):
        await self._update_state()

        chat = self._get(message, "chat")
        chat_name = self._display_name(chat) if chat else "Unknown"
        chat_id = self._message_chat_id(message)

        payload = {
            "message": await self._enriched_message(client, message, chat_id),
            "sender_name": await self._sender_name(message),
            "chat_name": chat_name,
            "chat_id": chat_id,
            "msg_id": self._message_id(message),
        }

        await self.bus.publish(Events.KURIGRAM_CHANNEL_MESSAGE, **payload)

    async def _on_chat_action(self, _client: Any, message: Message):
        await self._update_state()

        chat = self._get(message, "chat")
        chat_name = self._display_name(chat) if chat else "Unknown"

        action_text = "[Системное действие] Произошло системное событие в чате."

        new_members = self._get(message, "new_chat_members") or []
        if new_members:
            users_str = ", ".join(self._display_name(user) for user in new_members)
            action_text = f"[Системное действие] {users_str} присоединился к чату."
        elif self._get(message, "left_chat_member"):
            user_name = self._display_name(self._get(message, "left_chat_member"))
            action_text = f"[Системное действие] {user_name} покинул чат."
        elif self._get(message, "new_chat_title"):
            new_title = self._get(message, "new_chat_title")
            action_text = (
                f"[Системное действие] Название чата изменено на '{new_title}'."
            )
        elif self._get(message, "new_chat_photo") or self._get(
            message, "delete_chat_photo", default=False
        ):
            action_text = "[Системное действие] В чате обновлено или удалено фото."
        elif self._get(message, "pinned_message"):
            action_text = "[Системное действие] В чате закреплено новое сообщение."
        elif self._get(message, "group_chat_created", default=False) or self._get(
            message, "supergroup_chat_created", default=False
        ):
            action_text = f"[Системное действие] Чат '{chat_name}' был создан."
        elif self._get(message, "channel_chat_created", default=False):
            action_text = f"[Системное действие] Канал '{chat_name}' был создан."

        payload = {
            "message": action_text,
            "sender_name": "System",
            "chat_name": chat_name,
            "chat_id": self._message_chat_id(message),
        }

        await self.bus.publish(Events.KURIGRAM_CHAT_ACTION, **payload)

    # ==========================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # ==========================================================

    async def _fetch_recent_history(
        self, chat_id: Any, limit: int = 5, current_msg_id: int | None = None
    ) -> str:
        if chat_id is None:
            return ""

        try:
            client = self.tg_client.client()
            msgs = await self._get_chat_history(client, chat_id, limit=limit + 1)
            msgs = [
                msg
                for msg in msgs
                if current_msg_id is None or self._message_id(msg) != current_msg_id
            ]

            if not msgs:
                return ""

            lines = []
            for msg in self._history_to_chronological(msgs, limit=limit):
                formatted = await self._build_message_string(
                    client=client,
                    chat_id=chat_id,
                    msg=msg,
                    truncate_text_flag=True,
                )
                lines.append(formatted)

            return "\n" + "\n\n".join(lines)

        except Exception as e:
            system_logger.error(f"[Telegram Kurigram] Не удалось подтянуть предысторию: {e}")
            return ""

    async def _enriched_message(
        self,
        client: Any,
        message: Message,
        chat_id: Any,
        topic_id: int | None = None,
    ) -> str:
        fwd_info = await self._parse_forward(message)
        is_reply, reply_id = self._determine_reply(message, topic_id)
        reply_info = await self._parse_reply(client, chat_id, is_reply, reply_id)

        media_tag = self._parse_media(message)
        msg_text = self._message_text(message)
        reactions_info = await self._parse_reactions(message)
        buttons_info = self._parse_buttons(message)

        parts = [media_tag, msg_text, fwd_info, reply_info, reactions_info, buttons_info]
        return " ".join(filter(bool, parts)).strip() or "[Пустое сообщение]"

    async def _get_chat_history(self, client: Any, chat_id: Any, limit: int) -> list[Message]:
        history = await self._maybe_await(client.get_chat_history(chat_id, limit=limit))

        if history is None:
            return []

        if hasattr(history, "__aiter__"):
            messages = []
            async for msg in history:
                messages.append(msg)
            return messages

        return list(history) if isinstance(history, (list, tuple)) else [history]

    async def _get_message_by_id(
        self, client: Any, chat_id: Any, message_id: int | None
    ) -> Message | None:
        if chat_id is None or not message_id:
            return None

        for kwargs in ({"message_ids": message_id}, {"ids": message_id}):
            try:
                msg = await self._maybe_await(client.get_messages(chat_id, **kwargs))
                if isinstance(msg, list):
                    return msg[0] if msg else None
                return msg
            except (TypeError, ValueError):
                continue
            except Exception:
                return None

        try:
            msg = await self._maybe_await(client.get_messages(chat_id, message_id))
            if isinstance(msg, list):
                return msg[0] if msg else None
            return msg
        except Exception:
            return None

    async def _load_chat_description(self, client: Any, chat: Chat) -> str:
        chat_id = self._chat_id(chat)
        try:
            full_chat = await client.get_chat(chat_id)
            return self._clean_text(
                self._get(full_chat, "description") or self._get(full_chat, "bio")
            )
        except FloodWait:
            return ""
        except Exception:
            return ""

    async def _topic_info(
        self, client: Any, message: Message, chat_id: Any
    ) -> tuple[int | None, str | None]:
        topic_id = (
            self._int_or_none(self._get(message, "message_thread_id"))
            or self._int_or_none(self._get(message, "reply_to_top_message_id"))
            or self._topic_id_from_reply(message)
        )
        topic_name = None

        if topic_id:
            topic_msg = await self._get_message_by_id(client, chat_id, topic_id)
            topic = self._get(topic_msg, "forum_topic_created") if topic_msg else None
            topic_name = (
                self._clean_text(self._get(topic, "title"))
                or self._clean_text(self._get(topic, "name"))
                or self._clean_text(self._get(topic_msg, "text"))
            )

        return topic_id, topic_name

    async def _sender_name(self, message: Message) -> str:
        sender = self._get(message, "from_user", "sender")
        sender_id = self._chat_id(sender) or self._int_or_none(
            self._get(message, "from_user_id", "sender_id")
        )

        if sender:
            name = self._display_name(sender)
            return f"{name} (ID: {sender_id})" if sender_id else name

        sender_chat = self._get(message, "sender_chat")
        if sender_chat:
            name = self._display_name(sender_chat)
            return f"{name} [Анонимный Админ]"

        if sender_id:
            return f"Unknown (ID: {sender_id})"

        return "Unknown"

    async def _is_mentioned(self, message: Message) -> bool:
        if self._get(message, "mentioned", default=False):
            return True

        me = await self._ensure_me()
        if not me:
            return False

        text = self._message_text(message)
        me_id = self._chat_id(me)
        if self._has_text_mention_for_me(message, me_id):
            return True

        username = self._clean_text(self._get(me, "username")).lstrip("@")
        if username and re.search(rf"(?<!\w)@{re.escape(username)}(?!\w)", text, re.I):
            return True

        reply = self._get(message, "reply_to_message")
        reply_sender = self._get(reply, "from_user") if reply else None
        return bool(reply_sender and self._chat_id(reply_sender) == me_id)

    def _determine_reply(
        self, message: Message, topic_id: int | None
    ) -> tuple[bool, int | None]:
        reply = self._get(message, "reply_to_message")
        raw_reply = self._get(message, "reply_to")
        reply_id = self._message_id(reply) if reply else None
        if not reply_id:
            reply_id = (
                self._int_or_none(self._get(message, "reply_to_message_id"))
                or self._int_or_none(
                    self._get(raw_reply, "reply_to_msg_id", "reply_to_message_id")
                )
            )

        if not reply_id:
            return False, None

        if topic_id and str(reply_id) == str(topic_id):
            return False, None

        return True, reply_id

    def _parse_media(self, message: Message) -> str:
        if self._get(message, "service"):
            return "[Системное сообщение]"

        if self._get(message, "photo"):
            return "[Фотография]"

        sticker = self._get(message, "sticker")
        if sticker:
            emoji = self._clean_text(self._get(sticker, "emoji"))
            return f"[Стикер {emoji}]" if emoji else "[Стикер]"

        if self._get(message, "animation"):
            return "[GIF]"

        if self._get(message, "voice"):
            return "[Голосовое сообщение]"

        if self._get(message, "video") or self._get(message, "video_note"):
            return "[Видео]"

        if self._get(message, "audio"):
            return "[Аудио]"

        if self._get(message, "document"):
            return "[Файл]"

        if self._get(message, "poll"):
            return "[Опрос]"

        media = self._get(message, "media")
        media_name = self._clean_text(
            self._get(media, "value") or (media.__class__.__name__ if media else "")
        ).lower()
        if "photo" in media_name:
            return "[Фотография]"
        if "document" in media_name:
            return "[Файл]"
        return "[Медиа]" if media else ""

    async def _parse_forward(self, message: Message) -> str:
        forward_origin = self._get(message, "forward_origin")
        forward_from = self._get(forward_origin, "sender_user") or self._instance_attr(
            message, "forward_from"
        )
        if forward_from:
            return f"\n  ↳[Переслано от: {self._display_name(forward_from)}]"

        forward_chat = self._get(forward_origin, "chat", "sender_chat") or self._instance_attr(
            message, "forward_from_chat"
        )
        if forward_chat:
            return f"\n  ↳[Переслано от: {self._display_name(forward_chat)}]"

        forward_name = self._clean_text(
            self._get(forward_origin, "sender_user_name", "author_signature")
            or self._instance_attr(message, "forward_sender_name")
        )
        if forward_name:
            return f"\n  ↳[Переслано от: {forward_name}]"

        if (
            self._get(forward_origin, "date", "message_id")
            or self._instance_attr(message, "forward_date")
            or self._instance_attr(message, "forward_from_message_id")
            or self._instance_attr(message, "forward_signature")
        ):
            return "\n  ↳[Переслано]"

        return ""

    async def _parse_reply(
        self, client: Any, chat_id: Any, is_reply: bool, reply_id: int | None
    ) -> str:
        if not is_reply or not reply_id:
            return ""

        try:
            orig_msg = await self._get_message_by_id(client, chat_id, reply_id)
            if orig_msg:
                orig_sender = await self._sender_name(orig_msg)
            else:
                orig_sender = "Unknown"
            return f"\n  ↳ (В ответ на сообщение ID {reply_id} от {orig_sender})"
        except Exception:
            return f"\n  ↳ (В ответ на сообщение ID {reply_id})"

    async def _parse_reactions(self, message: Message) -> str:
        reactions = self._get(message, "reactions")
        if not reactions:
            return ""

        values = (
            self._get(reactions, "reactions")
            or self._get(reactions, "results")
            or self._get(reactions, "recent_reactions")
            or []
        )
        r_list = []
        for reaction in values:
            emoji = self._reaction_label(reaction)
            count = self._int_or_none(self._get(reaction, "count"))
            r_list.append(f"{emoji} x{count}" if count is not None else str(emoji))

        return f"\n  ↳[Реакции: {', '.join(r_list)}]" if r_list else ""

    def _parse_buttons(self, message: Message) -> str:
        markup = self._get(message, "reply_markup")
        keyboard = (
            self._get(markup, "inline_keyboard")
            or self._get(markup, "keyboard")
            or self._get(message, "buttons")
        )
        if not keyboard:
            return ""

        btn_texts = []
        for row in keyboard:
            buttons = self._get(row, "buttons") or row
            if not isinstance(buttons, (list, tuple)):
                buttons = [buttons]
            for button in buttons:
                text = self._clean_text(self._get(button, "text"))
                if text:
                    btn_texts.append(f"[{text}]")
        return f"\n  ↳[Кнопки: {', '.join(btn_texts)}]" if btn_texts else ""

    async def _build_message_string(
        self,
        client: Any,
        chat_id: Any,
        msg: Message,
        topic_id: int | None = None,
        truncate_text_flag: bool = False,
    ) -> str:
        read_status = " [Исходящее]" if self._get(msg, "outgoing", default=False) else ""
        sender_name = await self._sender_name(msg)
        is_reply, reply_id = self._determine_reply(msg, topic_id)

        text = self._message_text(msg)
        if truncate_text_flag:
            text = truncate_text(text, 1000, "... [Обрезано системой]")

        parts = [
            self._parse_media(msg),
            text,
            await self._parse_forward(msg),
            await self._parse_reply(client, chat_id, is_reply, reply_id),
            await self._parse_reactions(msg),
            self._parse_buttons(msg),
        ]

        final_text = " ".join(filter(bool, parts)) or "[Пустое сообщение]"
        msg_date = self._get(msg, "date")
        time_str = (
            format_datetime(msg_date, self.tg_client.timezone, fmt="%Y-%m-%d %H:%M")
            if msg_date
            else "Неизвестно"
        )

        topic_str = ""
        if not topic_id:
            t_id = (
                self._int_or_none(self._get(msg, "message_thread_id"))
                or self._int_or_none(self._get(msg, "reply_to_top_message_id"))
                or self._topic_id_from_reply(msg)
            )
            if t_id:
                topic_str = f" [Topic: {t_id}]"

        return (
            f"[{time_str}] [ID: {self._message_id(msg)}]{topic_str}{read_status} "
            f"{sender_name}: {final_text}"
        )

    def _message_text(self, message: Message) -> str:
        return self._clean_text(self._get(message, "text")) or self._clean_text(
            self._get(message, "caption", "message")
        )

    def _message_id(self, message: Message | None) -> int | None:
        if not message:
            return None
        return self._int_or_none(self._get(message, "id")) or self._int_or_none(
            self._get(message, "message_id")
        )

    def _message_chat_id(self, message: Message) -> Any:
        chat = self._get(message, "chat")
        if chat:
            return self._chat_id(chat)
        return self._int_or_none(self._get(message, "chat_id"))

    def _chat_id(self, chat: Any) -> int | None:
        return self._int_or_none(self._get(chat, "id"))

    def _display_name(self, entity: Any) -> str:
        if not entity:
            return "Unknown"

        title = self._clean_text(self._get(entity, "title"))
        if title:
            return title

        first_name = self._clean_text(self._get(entity, "first_name"))
        last_name = self._clean_text(self._get(entity, "last_name"))
        full_name = " ".join(part for part in (first_name, last_name) if part)
        if full_name:
            return full_name

        username = self._clean_text(self._get(entity, "username"))
        if username:
            return f"@{username}" if not username.startswith("@") else username

        return "Deleted Account" if self._get(entity, "is_deleted", default=False) else "Unknown"

    def _chat_type(self, chat: Chat) -> str:
        chat_type = self._get(chat, "type")
        return (
            self._clean_text(self._get(chat_type, "value"))
            or self._clean_text(chat_type)
        ).lower()

    def _is_private_chat(self, chat: Chat) -> bool:
        return self._chat_type(chat) in {"private", "bot"}

    def _is_group_chat(self, chat: Chat) -> bool:
        return self._chat_type(chat) in {"group", "supergroup"}

    def _is_channel_chat(self, chat: Chat) -> bool:
        return self._chat_type(chat) == "channel"

    def _topic_id_from_reply(self, message: Message) -> int | None:
        reply = self._get(message, "reply_to")
        top_id = self._int_or_none(
            self._get(reply, "reply_to_top_id", "reply_to_top_message_id")
        )
        if top_id:
            return top_id

        if self._get(reply, "forum_topic", default=False):
            return self._int_or_none(
                self._get(reply, "reply_to_msg_id", "reply_to_message_id")
            )

        return None

    def _has_text_mention_for_me(self, message: Message, me_id: int | None) -> bool:
        if me_id is None:
            return False

        entities = self._get(message, "entities", "caption_entities", default=[]) or []
        for entity in entities:
            mentioned_user = self._get(entity, "user")
            if mentioned_user and self._chat_id(mentioned_user) == me_id:
                return True

        return False

    def _reaction_label(self, reaction: Any) -> str:
        inner = self._get(reaction, "reaction")
        value = (
            self._get(reaction, "emoji", "emoticon")
            or self._get(inner, "emoji", "emoticon")
        )
        if value:
            return self._clean_text(value)

        if self._get(reaction, "custom_emoji_id", "document_id") or self._get(
            inner, "custom_emoji_id", "document_id"
        ):
            return "[CustomEmoji]"

        return "[Reaction]"

    def _history_to_chronological(
        self, messages: list[Message], limit: int | None = None
    ) -> list[Message]:
        if not messages:
            return []

        first_key = self._history_sort_key(messages[0])
        last_key = self._history_sort_key(messages[-1])
        newest_first = True
        if first_key is not None and last_key is not None:
            newest_first = first_key >= last_key

        if newest_first:
            selected = messages[:limit] if limit else messages
            return list(reversed(selected))

        selected = messages[-limit:] if limit else messages
        return list(selected)

    def _history_sort_key(self, message: Message) -> float | int | None:
        msg_date = self._get(message, "date")
        if isinstance(msg_date, datetime):
            return msg_date.timestamp()
        if isinstance(msg_date, (int, float)):
            return msg_date
        return self._message_id(message)

    def _peer_id(self, peer: Any) -> Any:
        if not peer:
            return "Unknown"

        try:
            return pyrogram_utils.get_peer_id(peer)
        except Exception:
            pass

        user_id = self._int_or_none(self._get(peer, "user_id"))
        if user_id is not None:
            return user_id

        chat_id = self._int_or_none(self._get(peer, "chat_id"))
        if chat_id is not None:
            return -chat_id

        channel_id = self._int_or_none(self._get(peer, "channel_id"))
        if channel_id is not None:
            return int(f"-100{channel_id}")

        return "Unknown"

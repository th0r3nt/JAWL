from datetime import datetime, timezone as dt_timezone
from inspect import isawaitable
from typing import Optional, Tuple, Any

from src.utils.dtime import format_datetime
from src.utils._tools import truncate_text


class KurigramMessageParser:
    """Утилита для глубокого парсинга сообщений Telegram.

    Основной ожидаемый формат - pyrogram.Message/Kurigram, с мягкими fallback-ами
    для raw-like объектов через duck typing.
    """

    _MISSING = object()

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
    async def _maybe_await(cls, value: Any) -> Any:
        if isawaitable(value):
            return await value
        return value

    @classmethod
    async def _call_optional(cls, obj: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = cls._get(obj, method_name)
        if not callable(method):
            return None
        return await cls._maybe_await(method(*args, **kwargs))

    @classmethod
    def _get_id(cls, obj: Any) -> Optional[int]:
        for attr in ("id", "user_id", "chat_id", "channel_id", "sender_id"):
            value = cls._get(obj, attr)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue

        from_id = cls._get(obj, "from_id", "peer_id")
        if from_id is not None and from_id is not obj:
            return cls._get_id(from_id)

        return None

    @classmethod
    def _message_id(cls, msg: Any) -> Optional[int]:
        for attr in ("id", "message_id"):
            value = cls._get(msg, attr)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue
        return None

    @classmethod
    def _message_sender_id(cls, msg: Any, sender: Any = None) -> Optional[int]:
        return (
            cls._get_id(sender)
            or cls._get_id(cls._get(msg, "from_user", "sender_chat", "sender"))
            or cls._get_id(cls._get(msg, "from_id"))
            or cls._get(msg, "sender_id")
        )

    @classmethod
    def _display_name(cls, entity: Any) -> str:
        if not entity:
            return ""

        title = cls._clean_text(cls._get(entity, "title"))
        if title:
            return title

        first_name = cls._clean_text(cls._get(entity, "first_name"))
        last_name = cls._clean_text(cls._get(entity, "last_name"))
        full_name = " ".join(part for part in (first_name, last_name) if part)
        if full_name:
            return full_name

        name = cls._clean_text(cls._get(entity, "name"))
        if name:
            return name

        username = cls._clean_text(cls._get(entity, "username"))
        if username:
            return f"@{username}" if not username.startswith("@") else username

        if cls._get(entity, "is_deleted", "deleted", default=False):
            return "Deleted Account"

        return ""

    @classmethod
    def _chat_type(cls, chat: Any) -> str:
        chat_type = cls._get(chat, "type")
        if chat_type is None:
            return ""
        value = cls._clean_text(cls._get(chat_type, "value")) or cls._clean_text(chat_type)
        return value.lower()

    @classmethod
    def _is_group_or_channel(cls, msg: Any) -> bool:
        if cls._get(msg, "is_group", default=False) or cls._get(msg, "is_channel", default=False):
            return True

        chat_type = cls._chat_type(cls._get(msg, "chat"))
        return chat_type in {"group", "supergroup", "channel"}

    @classmethod
    def _message_text(cls, msg: Any) -> str:
        return (
            cls._clean_text(cls._get(msg, "text"))
            or cls._clean_text(cls._get(msg, "caption"))
            or cls._clean_text(cls._get(msg, "message"))
            or cls._clean_text(cls._get(msg, "raw_text"))
        )

    @classmethod
    def _message_date(cls, msg: Any) -> datetime:
        value = cls._get(msg, "date")
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=dt_timezone.utc)
        return datetime.now(dt_timezone.utc)

    @classmethod
    def _topic_id_from_reply(cls, msg: Any) -> Optional[int]:
        reply = cls._get(msg, "reply_to")
        top_id = (
            cls._get(msg, "reply_to_top_message_id")
            or cls._get(msg, "reply_to_top_id")
            or cls._get(reply, "reply_to_top_id", "reply_to_top_message_id")
        )
        if top_id:
            try:
                return int(top_id)
            except (TypeError, ValueError):
                return None

        if cls._get(reply, "forum_topic", default=False):
            value = cls._get(reply, "reply_to_msg_id", "reply_to_message_id")
            try:
                return int(value) if value else None
            except (TypeError, ValueError):
                return None

        return None

    @classmethod
    async def _get_message_by_id(cls, client: Any, target_entity: Any, message_id: int) -> Any:
        targets = [target_entity]
        target_id = cls._get_id(target_entity)
        if target_id is not None and target_id != target_entity:
            targets.append(target_id)

        for target in targets:
            for kwargs in ({"message_ids": message_id}, {"ids": message_id}):
                try:
                    result = await cls._maybe_await(client.get_messages(target, **kwargs))
                    return result[0] if isinstance(result, list) and result else result
                except (TypeError, ValueError):
                    continue

        for target in targets:
            try:
                result = await cls._maybe_await(client.get_messages(target, message_id))
                return result[0] if isinstance(result, list) and result else result
            except Exception:
                continue

        return None

    @classmethod
    async def _resolve_peer(cls, client: Any, peer: Any) -> Any:
        for method_name in ("get_entity", "get_users", "get_chat"):
            try:
                result = await cls._call_optional(client, method_name, peer)
                if result:
                    return result
            except Exception:
                continue
        return None

    @classmethod
    def _reaction_label(cls, reaction: Any) -> str:
        value = (
            cls._get(reaction, "emoji")
            or cls._get(reaction, "emoticon")
            or cls._get(cls._get(reaction, "reaction"), "emoji", "emoticon")
        )
        if value:
            return cls._clean_text(value)
        if cls._get(reaction, "custom_emoji_id") or cls._get(
            cls._get(reaction, "reaction"), "document_id", "custom_emoji_id"
        ):
            return "[CustomEmoji]"
        return "[Reaction]"

    @classmethod
    def _media_matches(cls, msg: Any, media_value: Any, *needles: str) -> bool:
        for needle in needles:
            if cls._get(msg, needle) is not None:
                return True

        media_name = cls._clean_text(cls._get(media_value, "value")) or cls._clean_text(
            media_value.__class__.__name__ if media_value is not None else ""
        )
        media_name = media_name.lower()
        return any(needle in media_name for needle in needles)

    @staticmethod
    async def get_sender_name(msg: Any) -> str:
        sender = KurigramMessageParser._get(msg, "from_user", "sender")
        sender_chat = KurigramMessageParser._get(msg, "sender_chat")
        if not sender:
            try:
                sender = await KurigramMessageParser._call_optional(msg, "get_sender")
            except Exception:
                pass

        if sender:
            name = KurigramMessageParser._display_name(sender) or "Anonymous"
            sender_id = KurigramMessageParser._message_sender_id(msg, sender)
            return f"{name} (ID: {sender_id})" if sender_id else name

        if sender_chat:
            name = KurigramMessageParser._display_name(sender_chat) or "Anonymous"
            chat = KurigramMessageParser._get(msg, "chat")
            if KurigramMessageParser._get_id(sender_chat) == KurigramMessageParser._get_id(chat):
                return f"{name} [Анонимный Админ]"
            sender_id = KurigramMessageParser._get_id(sender_chat)
            return f"{name} (ID: {sender_id})" if sender_id else name

        # Если отправитель всё еще None, проверяем: возможно это анонимный админ.
        if KurigramMessageParser._is_group_or_channel(msg):
            chat = KurigramMessageParser._get(msg, "chat")
            if not chat:
                try:
                    chat = await KurigramMessageParser._call_optional(msg, "get_chat")
                except Exception:
                    pass

            if chat:
                name = KurigramMessageParser._display_name(chat)
                return f"{name} [Анонимный Админ]"

        sender_id = KurigramMessageParser._message_sender_id(msg)
        if sender_id:
            return f"Unknown (ID: {sender_id})"

        return "Unknown"

    @staticmethod
    def determine_reply(msg: Any, topic_id: Optional[int]) -> Tuple[bool, Optional[int]]:
        """Определяет, является ли сообщение reply (ответом на другое сообщение)."""

        reply_msg = KurigramMessageParser._get(msg, "reply_to_message")
        reply = KurigramMessageParser._get(msg, "reply_to")
        reply_id = (
            KurigramMessageParser._message_id(reply_msg)
            or KurigramMessageParser._get(msg, "reply_to_message_id")
            or KurigramMessageParser._get(reply, "reply_to_msg_id", "reply_to_message_id")
        )

        if not reply_id:
            return False, None

        top_id = KurigramMessageParser._topic_id_from_reply(msg)
        forum_topic = bool(top_id) or bool(KurigramMessageParser._get(reply, "forum_topic"))

        if forum_topic:
            is_actual_reply = False
            if top_id and str(reply_id) != str(top_id):
                is_actual_reply = True
        else:
            is_actual_reply = True

        if is_actual_reply and str(reply_id) == str(topic_id):
            is_actual_reply = False

        return is_actual_reply, reply_id

    @staticmethod
    def parse_media(msg: Any) -> str:
        """Определяет, какое именно медиа отправлено в сообщении."""

        if KurigramMessageParser._get(msg, "action", "service"):
            return "[Системное сообщение]"

        media = KurigramMessageParser._get(msg, "media")
        if not media and not any(
            KurigramMessageParser._get(msg, attr) is not None
            for attr in (
                "photo",
                "sticker",
                "animation",
                "gif",
                "voice",
                "video",
                "video_note",
                "document",
                "poll",
                "audio",
            )
        ):
            return ""

        if KurigramMessageParser._media_matches(msg, media, "photo"):
            return "[Фотография]"

        if KurigramMessageParser._media_matches(msg, media, "sticker"):
            sticker = KurigramMessageParser._get(msg, "sticker")
            file_obj = KurigramMessageParser._get(msg, "file")
            emoji = KurigramMessageParser._clean_text(
                KurigramMessageParser._get(sticker, "emoji")
                or KurigramMessageParser._get(file_obj, "emoji")
            )
            return f"[Стикер {emoji}]" if emoji else "[Стикер]"

        if KurigramMessageParser._media_matches(msg, media, "animation", "gif"):
            return "[GIF]"

        if KurigramMessageParser._media_matches(msg, media, "voice"):
            return "[Голосовое сообщение]"

        if KurigramMessageParser._media_matches(msg, media, "video", "video_note"):
            return "[Видео]"

        if KurigramMessageParser._media_matches(msg, media, "poll"):
            return "[Опрос]"

        if KurigramMessageParser._media_matches(msg, media, "audio"):
            return "[Аудио]"

        if KurigramMessageParser._media_matches(msg, media, "document"):
            return "[Файл]"

        return "[Медиа]"

    @staticmethod
    async def parse_forward(msg: Any) -> str:
        """Определяет, является ли сообщение пересланным."""

        forward_origin = KurigramMessageParser._get(msg, "forward_origin")
        fwd_from = KurigramMessageParser._get(msg, "fwd_from")
        forward_from = KurigramMessageParser._instance_attr(msg, "forward_from")
        forward_chat = KurigramMessageParser._instance_attr(msg, "forward_from_chat")
        forward_date = (
            KurigramMessageParser._get(
                forward_origin, "date", "message_id", "author_signature"
            )
            or KurigramMessageParser._instance_attr(msg, "forward_date")
            or KurigramMessageParser._instance_attr(msg, "forward_from_message_id")
            or KurigramMessageParser._instance_attr(msg, "forward_signature")
        )
        origin_sender = KurigramMessageParser._get(
            forward_origin, "sender_user", "sender_chat", "chat"
        )
        forward_name = (
            KurigramMessageParser._clean_text(
                KurigramMessageParser._instance_attr(msg, "forward_sender_name")
            )
            or KurigramMessageParser._clean_text(
                KurigramMessageParser._get(
                    forward_origin, "sender_user_name", "author_signature"
                )
            )
            or KurigramMessageParser._clean_text(KurigramMessageParser._get(fwd_from, "from_name"))
            or KurigramMessageParser._clean_text(
                KurigramMessageParser._get(fwd_from, "post_author")
            )
        )

        if not any(
            (fwd_from, forward_origin, forward_from, forward_chat, forward_name, forward_date)
        ):
            return ""

        try:
            fwd_sender = forward_from or forward_chat or origin_sender
            if not fwd_sender:
                fwd_sender = await KurigramMessageParser._call_optional(msg, "get_forward_sender")
            if fwd_sender:
                name = KurigramMessageParser._display_name(fwd_sender)
                return f"\n  ↳[Переслано от: {name or 'Unknown'}]"

            if forward_name:
                return f"\n  ↳[Переслано от: {forward_name}]"

        except Exception:
            pass

        return "\n  ↳[Переслано]"

    @staticmethod
    async def parse_reply(
        client: Any, target_entity: Any, is_reply: bool, reply_id: Optional[int]
    ) -> str:
        """Определяет ID сообщения и username отправителя."""

        if not is_reply or not reply_id:
            return ""

        try:
            orig_msg = await KurigramMessageParser._get_message_by_id(
                client, target_entity, int(reply_id)
            )
            orig_sender = (
                await KurigramMessageParser.get_sender_name(orig_msg) if orig_msg else "Unknown"
            )
            return f"\n  ↳ (В ответ на сообщение ID {reply_id} от {orig_sender})"

        except Exception:
            return f"\n  ↳ (В ответ на сообщение ID {reply_id})"

    @staticmethod
    async def parse_reactions(client: Any, msg: Any) -> str:
        """Определяет, есть ли реакции на сообщения."""

        reactions = KurigramMessageParser._get(msg, "reactions")
        if not reactions:
            return ""

        r_list = []
        pyrogram_reactions = KurigramMessageParser._get(reactions, "reactions")

        if pyrogram_reactions:
            for r in pyrogram_reactions:
                emo = KurigramMessageParser._reaction_label(r)
                count = KurigramMessageParser._get(r, "count")
                r_list.append(f"{emo} x{count}" if count else emo)

        elif KurigramMessageParser._get(reactions, "recent_reactions"):
            for r in KurigramMessageParser._get(reactions, "recent_reactions") or []:
                emo = KurigramMessageParser._reaction_label(r)
                try:
                    peer = await KurigramMessageParser._resolve_peer(
                        client, KurigramMessageParser._get(r, "peer_id")
                    )
                    name = KurigramMessageParser._display_name(peer) or "Unknown"
                    r_list.append(f"{emo} от {name}")
                except Exception:
                    r_list.append(f"{emo}")

        elif KurigramMessageParser._get(reactions, "results"):
            for r in KurigramMessageParser._get(reactions, "results") or []:
                emo = KurigramMessageParser._reaction_label(r)
                count = KurigramMessageParser._get(r, "count")
                r_list.append(f"{emo} x{count}" if count else emo)

        return f"\n  ↳[Реакции: {', '.join(r_list)}]" if r_list else ""

    @staticmethod
    def parse_buttons(msg: Any) -> str:
        """Определяет, есть ли inline кнопки под сообщением бота."""

        reply_markup = KurigramMessageParser._get(msg, "reply_markup")
        rows = KurigramMessageParser._get(
            reply_markup, "inline_keyboard"
        ) or KurigramMessageParser._get(
            reply_markup, "keyboard"
        ) or KurigramMessageParser._get(
            msg,
            "buttons",
        )
        if not rows:
            return ""

        btn_texts = []
        for row in rows:
            buttons = KurigramMessageParser._get(row, "buttons") or row
            if not isinstance(buttons, (list, tuple)):
                buttons = [buttons]
            for btn in buttons:
                text = KurigramMessageParser._clean_text(KurigramMessageParser._get(btn, "text"))
                if text:
                    btn_texts.append(f"[{text}]")

        return f"\n  ↳[Кнопки: {', '.join(btn_texts)}]" if btn_texts else ""

    @classmethod
    async def build_string(
        cls,
        client: Any,
        target_entity: Any,
        msg: Any,
        timezone: int,
        topic_id: Optional[int] = None,
        read_outbox_max_id: int = 0,
        truncate_text_flag: bool = False,
    ) -> str:
        """Собирает полное, мощно отформатированное сообщение."""

        read_status = ""
        msg_id = cls._message_id(msg) or 0
        if cls._get(msg, "out", "outgoing", default=False):
            read_status = (
                " [Прочитано]" if msg_id <= read_outbox_max_id else " [Не прочитано]"
            )

        sender_name = await cls.get_sender_name(msg)
        is_reply, reply_id = cls.determine_reply(msg, topic_id)

        text = cls._message_text(msg)
        if truncate_text_flag:
            text = truncate_text(text, 1000, "... [Обрезано системой]")

        parts = [
            cls.parse_media(msg),
            text,
            await cls.parse_forward(msg),
            await cls.parse_reply(client, target_entity, is_reply, reply_id),
            await cls.parse_reactions(client, msg),
            cls.parse_buttons(msg),
        ]

        final_text = " ".join(filter(bool, parts)) or "[Пустое сообщение]"
        time_str = format_datetime(cls._message_date(msg), timezone, fmt="%Y-%m-%d %H:%M")

        topic_str = ""
        if not topic_id:
            t_id = cls._topic_id_from_reply(msg)
            if t_id:
                topic_str = f" [Topic: {t_id}]"

        return f"[{time_str}] [ID: {msg_id}]{topic_str}{read_status} {sender_name}: {final_text}"

from typing import Optional, Tuple, Any
from telethon import utils
from src.utils.dtime import format_datetime

# TODO: может, перенести этот файл в отдельную папку telethon/utils/?
# Сейчас он в корне telethon/, моя тонкая душевная организация перфекциониста недовольна

class TelethonMessageParser:
    """Утилита для глубокого парсинга сообщений Telethon (реакции, реплаи, медиа, кнопки)."""

    @staticmethod
    def get_sender_name(msg: Any) -> str:
        if msg.sender:
            name = utils.get_display_name(msg.sender)
            return f"{name} (ID: {msg.sender_id})" if msg.sender_id else name
        elif msg.sender_id:
            return f"Unknown (ID: {msg.sender_id})"
        return "Unknown"

    @staticmethod
    def determine_reply(msg: Any, topic_id: Optional[int]) -> Tuple[bool, Optional[int]]:
        """Определяет, является ли сообщение reply (ответом на другое сообщение)."""

        if not msg.reply_to:
            return False, None

        reply_id = None
        is_actual_reply = False

        if getattr(msg.reply_to, "forum_topic", False):
            top_id = getattr(msg.reply_to, "reply_to_top_id", None)
            if top_id and msg.reply_to.reply_to_msg_id != top_id:
                is_actual_reply = True
                reply_id = msg.reply_to.reply_to_msg_id
        else:
            is_actual_reply = True
            reply_id = msg.reply_to.reply_to_msg_id

        if is_actual_reply and str(reply_id) == str(topic_id):
            is_actual_reply = False

        return is_actual_reply, reply_id

    @staticmethod
    def parse_media(msg: Any) -> str:
        """Определяет, какое именно медиа отправлено в сообщении."""

        if msg.action:
            return "[Системное сообщение]"

        if not msg.media:
            return ""

        if msg.photo:
            return "[Фотография]"

        if msg.sticker:
            emoji = getattr(msg.file, "emoji", "") if hasattr(msg, "file") else ""
            return f"[Стикер {emoji}]" if emoji else "[Стикер]"

        if getattr(msg, "gif", None):
            return "[GIF]"

        if msg.voice:
            return "[Голосовое сообщение]"

        if msg.video or msg.video_note:
            return "[Видео]"

        if msg.document:
            return "[Файл]"

        if msg.poll:
            return "[Опрос]"

        return "[Медиа]"

    @staticmethod
    async def parse_forward(msg: Any) -> str:
        """Определяет, является ли сообщение пересланным."""

        if not msg.fwd_from:
            return ""
        try:
            fwd_sender = await msg.get_forward_sender()
            if fwd_sender:
                return f"\n  ↳[Переслано от: {utils.get_display_name(fwd_sender)}]"

            elif msg.fwd_from.from_name:
                return f"\n  ↳[Переслано от: {msg.fwd_from.from_name}]"

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
            orig_msg = await client.get_messages(target_entity, ids=reply_id)
            if orig_msg and orig_msg.sender:
                orig_name = utils.get_display_name(orig_msg.sender)
                orig_sender = (
                    f"{orig_name} (ID: {orig_msg.sender_id})"
                    if orig_msg.sender_id
                    else orig_name
                )
            elif orig_msg and orig_msg.sender_id:
                orig_sender = f"Unknown (ID: {orig_msg.sender_id})"

            else:
                orig_sender = "Unknown"
            return f"\n  ↳ (В ответ на сообщение ID {reply_id} от {orig_sender})"

        except Exception:
            return f"\n  ↳ (В ответ на сообщение ID {reply_id})"

    @staticmethod
    async def parse_reactions(client: Any, msg: Any) -> str:
        """Определяет, есть ли реакции на сообщения."""

        if not getattr(msg, "reactions", None):
            return ""

        r_list = []

        if getattr(msg.reactions, "recent_reactions", None):
            for r in msg.reactions.recent_reactions:
                emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                try:
                    peer = await client.get_entity(r.peer_id)
                    name = utils.get_display_name(peer) or "Unknown"
                    r_list.append(f"{emo} от {name}")
                except Exception:
                    r_list.append(f"{emo}")

        elif getattr(msg.reactions, "results", None):
            for r in msg.reactions.results:
                emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                r_list.append(f"{emo} x{r.count}")

        return f"\n  ↳[Реакции: {', '.join(r_list)}]" if r_list else ""

    @staticmethod
    def parse_buttons(msg: Any) -> str:
        """Определяет, есть ли inline кнопки под сообщением бота. """
        
        if not getattr(msg, "buttons", None):
            return ""
        btn_texts = [f"[{btn.text}]" for row in msg.buttons for btn in row if btn.text]
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
        truncate_text: bool = False,
    ) -> str:
        """Собирает полное, мощно отформатированное сообщение."""

        read_status = ""
        if msg.out:
            read_status = " [Прочитано]" if msg.id <= read_outbox_max_id else " [Не прочитано]"

        sender_name = cls.get_sender_name(msg)
        is_reply, reply_id = cls.determine_reply(msg, topic_id)

        text = msg.text or ""
        if truncate_text and len(text) > 200:
            text = text[:200] + "... [Обрезано системой]"

        parts = [
            cls.parse_media(msg),
            text,
            await cls.parse_forward(msg),
            await cls.parse_reply(client, target_entity, is_reply, reply_id),
            await cls.parse_reactions(client, msg),
            cls.parse_buttons(msg),
        ]

        final_text = " ".join(filter(bool, parts)) or "[Пустое сообщение]"
        time_str = format_datetime(msg.date, timezone, fmt="%Y-%m-%d %H:%M")

        return f"[{time_str}] [ID: {msg.id}]{read_status} {sender_name}: {final_text}"

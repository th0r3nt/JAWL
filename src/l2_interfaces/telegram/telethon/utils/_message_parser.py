"""
Инструментарий для глубокого парсинга сложных MTProto-сообщений (Telethon).

Преобразует объекты Message, содержащие медиа, реплаи, форварды, кнопки и
реакции, в "плоские" и понятные для LLM текстовые строки.
"""

from typing import Optional, Tuple, Any
from telethon import utils

from src.utils.dtime import format_datetime
from src.utils._tools import truncate_text


class TelethonMessageParser:
    """Утилита для парсинга сообщений Telethon."""

    @staticmethod
    async def get_sender_name(msg: Any) -> str:
        """
        Вычисляет и форматирует имя отправителя сообщения.
        Учитывает анонимных администраторов в каналах/группах и удаленные аккаунты.

        Args:
            msg (Any): Объект Message Telethon.

        Returns:
            str: Человекочитаемое имя или 'Unknown'.
        """
        sender = msg.sender
        if not sender:
            try:
                # Пытаемся подтянуть отправителя, если его нет в локальном кэше
                sender = await msg.get_sender()
            except Exception:
                pass

        # Обработка анонимных админов (отправитель = сам чат)
        if not sender and (msg.is_group or msg.is_channel):
            chat = msg.chat
            if not chat:
                try:
                    chat = await msg.get_chat()
                except Exception:
                    pass

            if chat:
                name = utils.get_display_name(chat)
                return f"{name} [Анонимный Админ]"

        if sender:
            name = utils.get_display_name(sender)
            if not name:
                name = "Deleted Account" if getattr(sender, "deleted", False) else "Anonymous"
            return f"{name} (ID: {msg.sender_id})" if msg.sender_id else name

        elif msg.sender_id:
            return f"Unknown (ID: {msg.sender_id})"

        return "Unknown"

    @staticmethod
    def determine_reply(msg: Any, topic_id: Optional[int]) -> Tuple[bool, Optional[int]]:
        """
        Определяет, является ли сообщение ответом (реплаем), игнорируя системные
        связи внутри топиков (forum topics).

        Args:
            msg (Any): Сообщение Telethon.
            topic_id (Optional[int]): ID топика форума.

        Returns:
            Tuple[bool, Optional[int]]: (Является_ли_реплаем, ID_оригинального_сообщения)
        """
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
        """Возвращает текстовый тег медиа-вложения (если есть)."""
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
        """Формирует подпись, если сообщение было переслано (Forwarded)."""
        if not getattr(msg, "fwd_from", None):
            return ""

        fwd_sender = None
        try:
            fwd_sender = await msg.get_forward_sender()
        except Exception:
            pass

        if fwd_sender:
            name = utils.get_display_name(fwd_sender)
            fwd_id = getattr(fwd_sender, "id", "")
            id_str = f" (ID: {fwd_id})" if fwd_id else ""
            return f"\n  ↳[Переслано от: {name}{id_str}]"

        if getattr(msg.fwd_from, "from_name", None):
            return f"\n  ↳[Переслано от: {msg.fwd_from.from_name} (Скрытый аккаунт)]"

        if getattr(msg.fwd_from, "from_id", None):
            try:
                peer_id = utils.get_peer_id(msg.fwd_from.from_id)
                return f"\n  ↳[Переслано от: ID {peer_id}]"
            except Exception:
                pass

        return "\n  ↳[Переслано]"

    @staticmethod
    async def parse_reply(
        client: Any, target_entity: Any, is_reply: bool, reply_id: Optional[int]
    ) -> str:
        """Парсит автора и ID сообщения, на которое был дан ответ."""
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
        """Парсит эмодзи-реакции под сообщением."""
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
        """Парсит текст Inline-кнопок."""
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
        truncate_text_flag: bool = False,
    ) -> str:
        """
        Финальная сборка: объединяет все сущности в плоский Markdown текст,
        идеально приспособленный для чтения языковой моделью.
        """
        read_status = ""
        if msg.out:
            read_status = " [Прочитано]" if msg.id <= read_outbox_max_id else " [Не прочитано]"

        sender_name = await cls.get_sender_name(msg)
        is_reply, reply_id = cls.determine_reply(msg, topic_id)

        text = msg.text or ""
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
        time_str = format_datetime(msg.date, timezone, fmt="%Y-%m-%d %H:%M")

        topic_str = ""
        if (
            not topic_id
            and getattr(msg, "reply_to", None)
            and getattr(msg.reply_to, "forum_topic", False)
        ):
            t_id = msg.reply_to.reply_to_top_id or msg.reply_to.reply_to_msg_id
            if t_id:
                topic_str = f" [Topic: {t_id}]"

        return (
            f"[{time_str}] [ID: {msg.id}]{topic_str}{read_status} {sender_name}: {final_text}"
        )

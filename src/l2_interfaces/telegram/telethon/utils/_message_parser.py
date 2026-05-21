"""
Telethon Message Parser.

Converts complex MTProto Message objects (including forwards, replies,
inlines, and reactions) into clean, readable Markdown strings optimized for LLM attention.
"""

from typing import Optional, Tuple, Any
from telethon import utils

from src.utils.dtime import format_datetime
from src.utils._tools import truncate_text


class TelethonMessageParser:
    """Helper for parsing and formatting Telethon MTProto messages."""

    @staticmethod
    async def get_sender_name(msg: Any) -> str:
        """
        Resolves sender display name, handling anonymous admins or deleted profiles.

        Args:
            msg: Telethon Message object.

        Returns:
            str: Resolved name.
        """
        
        sender = msg.sender
        if not sender:
            try:
                sender = await msg.get_sender()
            except Exception:
                pass

        if not sender and (msg.is_group or msg.is_channel):
            chat = msg.chat
            if not chat:
                try:
                    chat = await msg.get_chat()
                except Exception:
                    pass

            if chat:
                name = utils.get_display_name(chat)
                return f"{name} [Anonymous Admin]"

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
        Identifies whether a message is an actual reply to another message,
        ignoring standard thread parent message bindings on Forums.

        Args:
            msg: Telethon Message object.
            topic_id: Thread topic ID.
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
        """
        Returns string tag representing attached media type.
        """

        if msg.action:
            return "[System Notification]"

        if not msg.media:
            return ""

        if msg.photo:
            return "[Photo]"

        if msg.sticker:
            emoji = getattr(msg.file, "emoji", "") if hasattr(msg, "file") else ""
            return f"[Sticker {emoji}]" if emoji else "[Sticker]"

        if getattr(msg, "gif", None):
            return "[GIF]"

        if msg.voice:
            return "[Voice Message]"

        if msg.video or msg.video_note:
            return "[Video]"

        if msg.document:
            return "[Document]"

        if msg.poll:
            return "[Poll]"

        return "[Media]"

    @staticmethod
    async def parse_forward(msg: Any) -> str:
        """
        Parses forward sender info if message is forwarded.
        """

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
            return f"\n  ↳[Forwarded from: {name}{id_str}]"

        if getattr(msg.fwd_from, "from_name", None):
            return f"\n  ↳[Forwarded from: {msg.fwd_from.from_name} (Hidden profile)]"

        if getattr(msg.fwd_from, "from_id", None):
            try:
                peer_id = utils.get_peer_id(msg.fwd_from.from_id)
                return f"\n  ↳[Forwarded from: ID {peer_id}]"
            except Exception:
                pass

        return "\n  ↳[Forwarded]"

    @staticmethod
    async def parse_reply(
        client: Any, target_entity: Any, is_reply: bool, reply_id: Optional[int]
    ) -> str:
        """
        Parses the reply's author and original message ID.
        """

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
            return f"\n  ↳ (In reply to message ID {reply_id} by {orig_sender})"
        except Exception:
            return f"\n  ↳ (In reply to message ID {reply_id})"

    @staticmethod
    async def parse_reactions(client: Any, msg: Any) -> str:
        """
        Parses emoji reactions under the message.
        """

        if not getattr(msg, "reactions", None):
            return ""

        r_list = []
        if getattr(msg.reactions, "recent_reactions", None):
            for r in msg.reactions.recent_reactions:
                emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                try:
                    peer = await client.get_entity(r.peer_id)
                    name = utils.get_display_name(peer) or "Unknown"
                    r_list.append(f"{emo} by {name}")
                except Exception:
                    r_list.append(f"{emo}")

        elif getattr(msg.reactions, "results", None):
            for r in msg.reactions.results:
                emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                r_list.append(f"{emo} x{r.count}")

        return f"\n  ↳[Reactions: {', '.join(r_list)}]" if r_list else ""

    @staticmethod
    def parse_buttons(msg: Any) -> str:
        """Parses inline keyboard button titles."""
        if not getattr(msg, "buttons", None):
            return ""
        btn_texts = [f"[{btn.text}]" for row in msg.buttons for btn in row if btn.text]
        return f"\n  ↳[Buttons: {', '.join(btn_texts)}]" if btn_texts else ""

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
        Main formatter: merges all parsed message data into a single Markdown string.
        """

        read_status = ""
        if msg.out:
            read_status = " [Read]" if msg.id <= read_outbox_max_id else " [Unread]"

        sender_name = await cls.get_sender_name(msg)
        is_reply, reply_id = cls.determine_reply(msg, topic_id)

        text = msg.text or ""
        if truncate_text_flag:
            text = truncate_text(text, 1000, "... [Truncated by system]")

        parts = [
            cls.parse_media(msg),
            text,
            await cls.parse_forward(msg),
            await cls.parse_reply(client, target_entity, is_reply, reply_id),
            await cls.parse_reactions(client, msg),
            cls.parse_buttons(msg),
        ]

        final_text = " ".join(filter(bool, parts)) or "[Empty Message]"
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

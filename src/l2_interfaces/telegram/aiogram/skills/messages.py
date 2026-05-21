"""
Bot skills (Aiogram) for working with messages.

Sending, deleting, editing, and pinning messages.
"""

from typing import Optional
from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class AiogramMessages:
    """Group of skills for manipulating messages in Telegram chats."""

    def __init__(self, aiogram_client: AiogramClient) -> None:
        self.client = aiogram_client

    @skill()
    async def send_message(
        self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None
    ) -> SkillResult:
        """
        Sends text message on behalf of the bot.
        """

        try:
            bot = self.client.bot()

            msg = await bot.send_message(
                chat_id=int(chat_id),
                text=text,
                reply_to_message_id=int(reply_to_message_id) if reply_to_message_id else None,
            )

            main_logger.info(f"[Telegram Aiogram] Message sent to {chat_id}")
            return SkillResult.ok(f"True. ID: {msg.message_id}")

        except ValueError:
            return SkillResult.fail("Error: Chat ID must be a number.")

        except Exception as e:
            if "bot was blocked" in str(e).lower():
                return SkillResult.fail("User blocked the bot. Sending is impossible.")
            return SkillResult.fail(f"Error sending message (Aiogram): {e}")

    @skill()
    async def delete_message(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Deletes message in chat.
        Requires admin privileges for other users' messages.
        """

        try:
            bot = self.client.bot()
            await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))

            main_logger.info(f"[Telegram Aiogram] Deleted message {message_id} in {chat_id}")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error deleting message (Aiogram): {e}")

    @skill()
    async def edit_message(self, chat_id: int, message_id: int, new_text: str) -> SkillResult:
        """
        Edits text of previously sent bot message.
        """

        try:
            bot = self.client.bot()
            await bot.edit_message_text(
                chat_id=int(chat_id), message_id=int(message_id), text=new_text
            )

            main_logger.info(f"[Telegram Aiogram] Message {message_id} edited")
            return SkillResult.ok("True")

        except Exception as e:
            if "message is not modified" in str(e).lower():
                return SkillResult.ok("True")
            return SkillResult.fail(f"Error editing message (Aiogram): {e}")

    @skill()
    async def pin_message(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Pins message in group.
        Requires admin privileges.
        """

        try:
            bot = self.client.bot()
            await bot.pin_chat_message(
                chat_id=int(chat_id), message_id=int(message_id), disable_notification=False
            )

            main_logger.info(f"[Telegram Aiogram] Message {message_id} pinned in {chat_id}")
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Error pinning message (Aiogram): {e}")

    @skill()
    async def unpin_message(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Unpins previously pinned message.
        """

        try:
            bot = self.client.bot()
            await bot.unpin_chat_message(chat_id=int(chat_id), message_id=int(message_id))

            main_logger.info(f"[Telegram Aiogram] Message {message_id} unpinned in {chat_id}")
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Error unpinning message (Aiogram): {e}")

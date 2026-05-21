"""
Telethon Reactions Skills.

Provides skills to set and remove emoji reactions on messages.
"""

from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class TelethonReactions:
    """Group of skills for managing message reactions."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def set_reaction(self, chat_id: int, message_id: int, reaction: str) -> SkillResult:
        """
        Sets emoji reaction on message.
        """
        try:
            client = self.tg_client.client()

            await client(
                SendReactionRequest(
                    peer=int(chat_id),
                    msg_id=int(message_id),
                    reaction=[ReactionEmoji(emoticon=reaction)],
                )
            )

            main_logger.info(
                f"[Telegram Telethon] Reaction '{reaction}' set on message {message_id} in chat {chat_id}"
            )
            return SkillResult.ok("True")

        except Exception as e:
            msg = f"Error setting reaction: {e}"
            if "ReactionInvalidError" in str(e) or "REACTION_INVALID" in str(e):
                return SkillResult.fail(
                    "Error: This emoji is not supported or is disabled by chat settings."
                )
            return SkillResult.fail(msg)

    @skill()
    async def remove_reaction(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Removes reaction from message.
        """

        try:
            client = self.tg_client.client()

            # Empty list [] removes all reactions set by current account
            await client(
                SendReactionRequest(peer=int(chat_id), msg_id=int(message_id), reaction=[])
            )

            main_logger.info(
                f"[Telegram Telethon] Reaction cleared from message {message_id} in chat {chat_id}"
            )
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error removing reaction: {e}")

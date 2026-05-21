"""
Moderation skills for the bot (Aiogram).

Note: bots can ban users ONLY in groups/supergroups/channels.
Global Blacklist for bots does not exist — in DMs, the bot can
simply ignore the blocked user in the code logic itself.
"""

from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class AiogramModeration:
    """Administrative control skills group (bans and unbans)."""

    def __init__(self, aiogram_client: AiogramClient) -> None:
        self.client = aiogram_client

    @skill()
    async def ban_user(self, chat_id: int, user_id: int) -> SkillResult:
        """
        Bans user from group or supergroup.
        Requires admin privileges.
        """

        try:
            bot = self.client.bot()

            # In aiogram, ban_chat_member excludes the user from the chat permanently
            await bot.ban_chat_member(chat_id=int(chat_id), user_id=int(user_id))

            msg = f"User {user_id} banned in chat {chat_id} (Aiogram)."
            main_logger.info(f"[Telegram Aiogram] {msg}")
            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Error: User and chat IDs must be numbers.")
        except Exception as e:
            return SkillResult.fail(f"Error blocking user (Aiogram): {e}")

    @skill()
    async def unban_user(self, chat_id: int, user_id: int) -> SkillResult:
        """
        Unbans user in group.
        """

        try:
            bot = self.client.bot()

            # unban_chat_member lifts the ban
            await bot.unban_chat_member(chat_id=int(chat_id), user_id=int(user_id))

            msg = f"User {user_id} unbanned in chat {chat_id} (Aiogram)."
            main_logger.info(f"[Telegram Aiogram] {msg}")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error unblocking user (Aiogram): {e}")

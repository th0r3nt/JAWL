"""
Bot skills for reading chat lists and their metadata (Aiogram).

Note: limited by Bot API constraints. The bot does not have access to the global list
of its dialogues, so it can only "see" those chats it has interacted with
since the system started (MRU cache).
"""

from src.l2_interfaces.telegram.aiogram.state import AiogramState
from src.l2_interfaces.telegram.aiogram.client import AiogramClient

from src.l3_agent.skills.registry import SkillResult, skill


class AiogramChats:
    """Skills for interacting with the active chats list."""

    def __init__(self, aiogram_client: AiogramClient, state: AiogramState) -> None:
        """
        Initializes skills.

        Args:
            aiogram_client (AiogramClient): Aiogram client.
            state (AiogramState): Interface state with dialogues cache.
        """

        self.client = aiogram_client
        self.state = state

    @skill()
    async def get_chats(self, limit: int = 10) -> SkillResult:
        """
        Returns list of recent chats the bot interacted with.
        """

        try:
            if not self.state._chats_cache:
                return SkillResult.ok(
                    "Chat list is empty. No one wrote to the bot after launch."
                )

            # Take from state cache (where freshest are at the end), reverse, and slice by limit
            lines = list(self.state._chats_cache.values())[::-1][:limit]

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error retrieving chats list (Aiogram): {e}")

    @skill()
    async def get_chat_info(self, chat_id: int) -> SkillResult:
        """
        Returns detailed meta-information about specific chat.
        """

        try:
            bot = self.client.bot()
            chat = await bot.get_chat(int(chat_id))

            lines = [f"Chat {chat_id} info:"]
            lines.append(f"Type: {chat.type}")
            lines.append(
                f"Title/Name: {chat.title or chat.full_name or chat.username or 'Unknown'}"
            )

            if chat.description:
                lines.append(f"Description: {chat.description}")

            # For groups we can get participants count
            if chat.type in ("group", "supergroup", "channel"):
                count = await bot.get_chat_member_count(int(chat_id))
                lines.append(f"Participants count: {count}")

            return SkillResult.ok("\n".join(lines))

        except ValueError:
            return SkillResult.fail(f"Error: Chat ID must be a number ({chat_id}).")

        except Exception as e:
            if "chat not found" in str(e).lower():
                return SkillResult.fail(
                    "The bot did not find this chat. Perhaps it was deleted or the user blocked the bot."
                )
            return SkillResult.fail(f"Error retrieving chat {chat_id} info (Aiogram): {e}")

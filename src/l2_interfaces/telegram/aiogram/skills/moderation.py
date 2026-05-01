"""
Навыки модерации для бота (Aiogram).

Внимание: боты могут банить пользователей ТОЛЬКО в группах/супергруппах/каналах.
Глобального ЧС (Черного Списка) для ботов не существует — в ЛС бот может
просто игнорировать заблокированного пользователя в логике самого кода.
"""

from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class AiogramModeration:
    """Группа навыков административного контроля (баны и разбаны)."""

    def __init__(self, aiogram_client: AiogramClient) -> None:
        self.client = aiogram_client

    @skill()
    async def ban_user(self, chat_id: int, user_id: int) -> SkillResult:
        """
        Банит (исключает навсегда) пользователя из указанной группы или супергруппы.
        Для работы навыка бот должен обладать правами администратора.

        Args:
            chat_id (int): ID группы/канала.
            user_id (int): ID нарушителя.
        """
        try:
            bot = self.client.bot()

            # В aiogram ban_chat_member навсегда исключает пользователя из чата
            await bot.ban_chat_member(chat_id=int(chat_id), user_id=int(user_id))

            msg = f"Пользователь {user_id} забанен в чате {chat_id} (Aiogram)."
            system_logger.info(f"[Telegram Aiogram] {msg}")
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при блокировке пользователя (Aiogram): {e}")

    @skill()
    async def unban_user(self, chat_id: int, user_id: int) -> SkillResult:
        """
        Разбанивает пользователя в группе (удаляет из локального ЧС чата).

        Args:
            chat_id (int): ID группы/канала.
            user_id (int): ID пользователя для амнистии.
        """
        try:
            bot = self.client.bot()

            # unban_chat_member снимает бан
            await bot.unban_chat_member(chat_id=int(chat_id), user_id=int(user_id))

            msg = f"Пользователь {user_id} разбанен в чате {chat_id} (Aiogram)."
            system_logger.info(f"[Telegram Aiogram] {msg}")
            return SkillResult.ok(msg)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при разблокировке пользователя (Aiogram): {e}")

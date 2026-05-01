"""
Навыки агента для проставления или снятия эмодзи-реакций (Telethon).
"""

from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class TelethonReactions:
    """Группа навыков управления реакциями на сообщения."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def set_reaction(self, chat_id: int, message_id: int, reaction: str) -> SkillResult:
        """
        Ставит эмодзи-реакцию (например, '👍', '🔥', '❤') на указанное сообщение.
        Если ваша реакция уже стоит, она будет заменена на новую.

        Args:
            chat_id: ID чата.
            message_id: ID сообщения.
            reaction: Эмодзи-символ.
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

            system_logger.info(
                f"[Telegram Telethon] Реакция '{reaction}' поставлена на сообщение {message_id} в чате {chat_id}"
            )
            return SkillResult.ok(f"Реакция '{reaction}' успешно установлена.")

        except Exception as e:
            msg = f"Ошибка при установке реакции: {e}"
            if "ReactionInvalidError" in str(e) or "REACTION_INVALID" in str(e):
                return SkillResult.fail(
                    "Ошибка: Данный эмодзи не поддерживается или запрещен настройками этого чата."
                )
            return SkillResult.fail(msg)

    @skill()
    async def remove_reaction(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Убирает вашу текущую реакцию с сообщения.
        """
        try:
            client = self.tg_client.client()

            # Пустой массив [] снимает все установленные пользователем реакции
            await client(
                SendReactionRequest(peer=int(chat_id), msg_id=int(message_id), reaction=[])
            )

            system_logger.info(
                f"[Telegram Telethon] Реакция снята с сообщения {message_id} в чате {chat_id}"
            )
            return SkillResult.ok("Реакция успешно удалена.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении реакции: {e}")

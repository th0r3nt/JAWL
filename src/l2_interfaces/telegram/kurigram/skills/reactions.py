from typing import Union

from src.l2_interfaces.telegram.kurigram.client import KurigramClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils._tools import parse_int_or_str
from src.utils.logger import system_logger


class KurigramReactions:
    """
    Навыки агента для управления эмодзи-реакциями на сообщения.
    """

    def __init__(self, tg_client: KurigramClient):
        self.tg_client = tg_client

    @skill()
    async def set_reaction(
        self, chat_id: Union[int, str], message_id: int, reaction: str
    ) -> SkillResult:
        """
        Ставит эмодзи-реакцию на указанное сообщение.
        Если реакция уже стоит, она будет заменена на новую.
        """
        try:
            client = self.tg_client.client()
            await client.send_reaction(
                chat_id=parse_int_or_str(chat_id),
                message_id=int(message_id),
                emoji=reaction,
            )

            system_logger.info(
                f"[Telegram Kurigram] Реакция '{reaction}' поставлена на сообщение {message_id} в чате {chat_id}"
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
    async def remove_reaction(
        self, chat_id: Union[int, str], message_id: int
    ) -> SkillResult:
        """
        Убирает вашу текущую реакцию с сообщения (если она была установлена).
        """
        try:
            client = self.tg_client.client()
            await client.send_reaction(
                chat_id=parse_int_or_str(chat_id), message_id=int(message_id)
            )

            system_logger.info(f"[Telegram Kurigram] Реакция снята с сообщения {message_id} в чате {chat_id}")
            return SkillResult.ok("Реакция успешно удалена.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении реакции: {e}")

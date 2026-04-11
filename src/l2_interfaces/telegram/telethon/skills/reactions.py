from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class TelethonReactions:
    """
    Навыки агента для управления эмодзи-реакциями на сообщения.
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    @skill()
    async def set_reaction(self, chat_id: int, message_id: int, reaction: str) -> SkillResult:
        """
        Ставит эмодзи-реакцию на указанное сообщение.
        Если реакция уже стоит, она будет заменена на новую.
        """
        try:
            client = self.tg_client.client()

            # Telethon сам разберется с преобразованием строки в нужный тип ReactionEmoji
            await client.send_reaction(
                entity=int(chat_id), message=int(message_id), reaction=reaction
            )

            system_logger.info(
                f"[Agent Action] Реакция '{reaction}' поставлена на сообщение {message_id} в чате {chat_id}"
            )
            return SkillResult.ok(f"Реакция '{reaction}' успешно установлена.")

        except Exception as e:
            msg = f"Ошибка при установке реакции: {e}"
            system_logger.error(f"[Agent Action Result] {msg}")

            # Подсказка для агента, если в чате запрещены конкретные эмодзи
            if "ReactionInvalidError" in str(e) or "REACTION_INVALID" in str(e):
                return SkillResult.fail(
                    "Ошибка: Данный эмодзи не поддерживается или запрещен настройками этого чата."
                )

            return SkillResult.fail(msg)

    @skill()
    async def remove_reaction(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Убирает вашу текущую реакцию с сообщения (если она была установлена).
        """
        try:
            client = self.tg_client.client()

            # Передача None снимает текущую реакцию пользователя
            await client.send_reaction(
                entity=int(chat_id), message=int(message_id), reaction=None
            )

            system_logger.info(
                f"[Agent Action] Реакция снята с сообщения {message_id} в чате {chat_id}"
            )
            return SkillResult.ok("Реакция успешно удалена.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении реакции: {e}")

from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class AiogramMessages:
    """
    Навыки бота (Aiogram) для работы с сообщениями.
    Отправка, удаление и редактирование.
    """

    def __init__(self, aiogram_client: AiogramClient):
        self.client = aiogram_client

    @skill()
    async def send_message(
        self, chat_id: int, text: str, reply_to_message_id: int = None
    ) -> SkillResult:
        """Отправляет текстовое сообщение от лица бота."""

        try:
            bot = self.client.bot()

            msg = await bot.send_message(
                chat_id=int(chat_id),
                text=text,
                reply_to_message_id=reply_to_message_id and int(reply_to_message_id),
            )

            system_logger.info(f"Отправлено сообщение в {chat_id} (Aiogram)")
            return SkillResult.ok(f"Сообщение успешно отправлено. ID: {msg.message_id}")

        except ValueError:
            return SkillResult.fail("Ошибка: ID чата должен быть числом.")
        except Exception as e:
            msg = f"Ошибка при отправке сообщения (Aiogram): {e}"
            system_logger.error(f"[Agent Action Result] {msg}")

            if "bot was blocked" in str(e).lower():
                return SkillResult.fail("Пользователь заблокировал бота. Отправка невозможна.")
            return SkillResult.fail(msg)

    @skill()
    async def delete_message(self, chat_id: int, message_id: int) -> SkillResult:
        """Удаляет сообщение в чате (требуются права администратора в группах)."""

        try:
            bot = self.client.bot()
            await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))

            system_logger.info(f"Удалено сообщение {message_id} в {chat_id}")
            return SkillResult.ok(f"Сообщение {message_id} успешно удалено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении сообщения (Aiogram): {e}")

    @skill()
    async def edit_message(self, chat_id: int, message_id: int, new_text: str) -> SkillResult:
        """Изменяет текст уже отправленного ботом сообщения."""
        
        try:
            bot = self.client.bot()
            await bot.edit_message_text(
                chat_id=int(chat_id), message_id=int(message_id), text=new_text
            )

            system_logger.info(f"Сообщение {message_id} отредактировано")
            return SkillResult.ok(f"Текст сообщения {message_id} успешно изменен.")

        except Exception as e:
            if "message is not modified" in str(e).lower():
                return SkillResult.ok(
                    "Сообщение не изменено (новый текст совпадает со старым)."
                )
            return SkillResult.fail(f"Ошибка при редактировании сообщения (Aiogram): {e}")

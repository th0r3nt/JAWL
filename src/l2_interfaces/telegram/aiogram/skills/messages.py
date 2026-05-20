"""
Навыки бота (Aiogram) для работы с сообщениями.
Отправка, удаление, редактирование и закрепление сообщений.
"""

from typing import Optional
from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class AiogramMessages:
    """Группа навыков для манипуляции с сообщениями в чатах Telegram."""

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

            main_logger.info(f"[Telegram Aiogram] Отправлено сообщение в {chat_id}")
            return SkillResult.ok(f"True. ID: {msg.message_id}")

        except ValueError:
            return SkillResult.fail("Ошибка: ID чата должен быть числом.")

        except Exception as e:
            if "bot was blocked" in str(e).lower():
                return SkillResult.fail("Пользователь заблокировал бота. Отправка невозможна.")
            return SkillResult.fail(f"Ошибка при отправке сообщения (Aiogram): {e}")

    @skill()
    async def delete_message(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Deletes message in chat. 
        Requires admin privileges for other users' messages.
        """

        try:
            bot = self.client.bot()
            await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))

            main_logger.info(f"[Telegram Aiogram] Удалено сообщение {message_id} в {chat_id}")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении сообщения (Aiogram): {e}")

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

            main_logger.info(f"[Telegram Aiogram] Сообщение {message_id} отредактировано")
            return SkillResult.ok("True")

        except Exception as e:
            if "message is not modified" in str(e).lower():
                return SkillResult.ok("True")
            return SkillResult.fail(f"Ошибка при редактировании сообщения (Aiogram): {e}")

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

            main_logger.info(
                f"[Telegram Aiogram] Сообщение {message_id} закреплено в {chat_id}"
            )
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при закреплении сообщения (Aiogram): {e}")

    @skill()
    async def unpin_message(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Unpins previously pinned message.
        """
        
        try:
            bot = self.client.bot()
            await bot.unpin_chat_message(chat_id=int(chat_id), message_id=int(message_id))

            main_logger.info(
                f"[Telegram Aiogram] Сообщение {message_id} откреплено в {chat_id}"
            )
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при откреплении сообщения (Aiogram): {e}")

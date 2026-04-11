from datetime import timedelta

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class TelethonMessages:
    """
    Навыки агента для прямого взаимодействия с сообщениями (отправка, удаление, редактирование).
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    @skill()
    async def send_message(
        self,
        to_id: int,
        text: str,
        reply_to_message_id: int = None,
        is_silent: bool = False,
        time_delay: int = None,
    ) -> SkillResult:
        """
        Отправляет текстовое сообщение.
        """
        try:
            client = self.tg_client.client()

            kwargs = {
                "entity": int(to_id),
                "message": text,
                "silent": is_silent,
            }

            if reply_to_message_id:
                kwargs["reply_to"] = int(reply_to_message_id)

            if time_delay:
                # В Telegram отложенные сообщения можно ставить минимум на 10 секунд вперед
                delay_sec = max(10, int(time_delay))
                kwargs["schedule"] = timedelta(seconds=delay_sec)

            sent_msg = await client.send_message(**kwargs)

            # Если сообщение отложено, Telethon возвращает объект с немного другой структурой,
            # но sent_msg.id всё равно доступен.
            schedule_info = f" (отложено на {time_delay} сек)" if time_delay else ""
            msg = f"Сообщение успешно отправлено{schedule_info}. ID: {sent_msg.id}"

            system_logger.info(f"[Agent Action] Отправлено сообщение в {to_id}")
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: ID (to_id или reply_to) должны быть числами.")
        
        except Exception as e:
            msg = f"Ошибка при отправке сообщения: {e}"
            system_logger.error(f"[Agent Action Result] {msg}")
            return SkillResult.fail(msg)

    @skill()
    async def forward_message(self, msg_id: int, from_id: int, to_id: int) -> SkillResult:
        """Пересылает сообщение из одного чата в другой."""
        try:
            client = self.tg_client.client()
            await client.forward_messages(
                entity=int(to_id), messages=int(msg_id), from_peer=int(from_id)
            )

            system_logger.info(f"[Agent Action] Пересылка сообщения {msg_id} в {to_id}")
            return SkillResult.ok(f"Сообщение {msg_id} успешно переслано.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при пересылке сообщения: {e}")

    @skill()
    async def delete_message(self, msg_id: int, chat_id: int) -> SkillResult:
        """Удаляет сообщение (для себя и для всех, если есть права)."""
        try:
            client = self.tg_client.client()
            # Telethon принимает ID чата и список ID сообщений
            await client.delete_messages(entity=int(chat_id), message_ids=[int(msg_id)])

            system_logger.info(f"[Agent Action] Сообщение {msg_id} удалено в чате {chat_id}")
            return SkillResult.ok(f"Сообщение {msg_id} успешно удалено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении сообщения: {e}")

    @skill()
    async def edit_message(self, msg_id: int, new_text: str, chat_id: int) -> SkillResult:
        """Изменяет текст уже отправленного сообщения."""
        try:
            client = self.tg_client.client()
            await client.edit_message(entity=int(chat_id), message=int(msg_id), text=new_text)

            system_logger.info(f"[Agent Action] Сообщение {msg_id} отредактировано")
            return SkillResult.ok(f"Текст сообщения {msg_id} успешно изменен.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при редактировании сообщения: {e}")

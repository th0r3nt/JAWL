from telethon import utils

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class TelethonChats:
    """
    Навыки для работы со списком чатов и чтения сообщений.
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    @skill()
    async def get_chats(self, limit: int = 10) -> SkillResult:
        """Возвращает список последних чатов (пользователи, группы, каналы)."""
        try:
            client = self.tg_client.client()
            chats = []

            async for dialog in client.iter_dialogs(limit=limit):
                chat_type = (
                    "User" if dialog.is_user else "Group" if dialog.is_group else "Channel"
                )
                unread = (
                    f" [Непрочитанных: {dialog.unread_count}]"
                    if dialog.unread_count > 0
                    else ""
                )
                chats.append(
                    f"- {chat_type} | ID: `{dialog.id}` | Название: {dialog.name}{unread}"
                )

            if not chats:
                return SkillResult.ok("Список чатов пуст.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            msg = f"Ошибка при получении списка чатов: {e}"
            system_logger.error(f"[Agent Action Result] {msg}")
            return SkillResult.fail(msg)

    @skill()
    async def get_unread_chats(self) -> SkillResult:
        """Возвращает список чатов, в которых есть непрочитанные сообщения."""
        try:
            client = self.tg_client.client()
            chats = []

            # Ограничиваем скан первыми 50 диалогами, чтобы не нагружать API
            async for dialog in client.iter_dialogs(limit=50):
                if dialog.unread_count > 0:
                    chat_type = "User" if dialog.is_user else "Group/Channel"
                    chats.append(
                        f"- {chat_type} | ID: `{dialog.id}` | Название: **{dialog.name}** | Непрочитанных: {dialog.unread_count}"
                    )

            if not chats:
                return SkillResult.ok("Нет непрочитанных сообщений.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске непрочитанных чатов: {e}")

    @skill()
    async def read_chat(self, chat_id: int, limit: int = 10) -> SkillResult:
        """
        Читает историю указанного чата.
        Включает медиа, системные уведомления и контекст ответов (replies).
        """
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(int(chat_id))

            messages = []
            async for msg in client.iter_messages(target_entity, limit=limit):
                # 1. Отправитель
                sender_name = "Unknown"
                if msg.sender:
                    sender_name = utils.get_display_name(msg.sender)

                # 2. Формирование контента (Медиа + Текст + Системные действия)
                content_parts = []

                if msg.action:
                    content_parts.append("[Системное сообщение]")

                if msg.media:
                    if msg.photo:
                        content_parts.append("[Фотография]")
                    elif msg.voice:
                        content_parts.append("[Голосовое сообщение]")
                    elif msg.video or msg.video_note:
                        content_parts.append("[Видео]")
                    elif msg.document:
                        content_parts.append("[Файл]")
                    elif msg.poll:
                        content_parts.append("[Опрос]")
                    else:
                        content_parts.append("[Медиа]")

                if msg.text:
                    content_parts.append(msg.text)

                final_text = " ".join(content_parts) if content_parts else "[Пустое сообщение]"

                # Обработка Reply (Ответов)
                reply_context = ""
                if msg.is_reply and msg.reply_to_msg_id:
                    try:
                        # Делаем запрос к оригинальному сообщению, чтобы узнать автора
                        orig_msg = await msg.get_reply_message()
                        orig_sender = "Unknown"
                        if orig_msg and orig_msg.sender:
                            orig_sender = utils.get_display_name(orig_msg.sender)

                        reply_context = f"\n  ↳ (В ответ на сообщение ID {msg.reply_to_msg_id} от {orig_sender})"
                    except Exception:
                        # Если не удалось получить (удалено или скрыто)
                        reply_context = (
                            f"\n  ↳ (В ответ на сообщение ID {msg.reply_to_msg_id})"
                        )

                # 4. Сборка итоговой строки
                time_str = msg.date.strftime("%Y-%m-%d %H:%M")
                messages.append(
                    f"[{time_str}] [ID: {msg.id}] {sender_name}: {final_text}{reply_context}"
                )

            if not messages:
                return SkillResult.ok("В этом чате нет сообщений.")

            # Разворачиваем, чтобы диалог читался сверху вниз (старые -> новые)
            messages.reverse()
            return SkillResult.ok("\n\n".join(messages))

        except ValueError:
            return SkillResult.fail(f"Ошибка: Некорректный ID чата ({chat_id}).")
        
        except Exception as e:
            msg = f"Ошибка при чтении чата {chat_id}: {e}"
            system_logger.error(f"[Agent Action Result] {msg}")
            return SkillResult.fail(msg)

    @skill()
    async def mark_as_read(self, chat_id: int) -> SkillResult:
        """Помечает все сообщения в чате как прочитанные."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(int(chat_id))

            await client.send_read_acknowledge(target_entity)

            system_logger.info(f"[Agent Action] Чат {chat_id} помечен как прочитанный.")
            return SkillResult.ok(f"Чат {chat_id} успешно помечен как прочитанный.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при пометке чата {chat_id} как прочитанного: {e}")

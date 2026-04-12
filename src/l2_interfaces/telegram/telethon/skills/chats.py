import re
from datetime import timezone, timedelta
from telethon import utils
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

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
                tz = timezone(timedelta(hours=self.tg_client.timezone))
                time_str = msg.date.astimezone(tz).strftime("%Y-%m-%d %H:%M")
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
            return SkillResult.fail(msg)

    @skill()
    async def mark_as_read(self, chat_id: int) -> SkillResult:
        """Помечает все сообщения в чате как прочитанные."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(int(chat_id))

            await client.send_read_acknowledge(target_entity)

            system_logger.info(f"Чат {chat_id} помечен как прочитанный.")
            return SkillResult.ok(f"Чат {chat_id} успешно помечен как прочитанный.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при пометке чата {chat_id} как прочитанного: {e}")

    @skill()
    async def search_public_chats(self, query: str, limit: int = 5) -> SkillResult:
        """Ищет публичные группы и каналы в глобальном поиске Telegram по запросу."""
        try:
            client = self.tg_client.client()

            # Выполняем запрос к глобальному поиску
            result = await client(SearchRequest(q=query, limit=limit))

            chats = []
            # result.chats содержит найденные публичные сущности (каналы/группы)
            for chat in result.chats:
                chat_type = "Channel" if getattr(chat, "broadcast", False) else "Group"
                username = f"@{chat.username}" if getattr(chat, "username", None) else "Нет"
                chats.append(
                    f"- {chat_type} | ID: `{chat.id}` | Название: {chat.title} | Юзернейм: {username}"
                )

            if not chats:
                return SkillResult.ok(f"По глобальному запросу '{query}' ничего не найдено.")

            system_logger.info(f"Глобальный поиск чатов по запросу '{query}'")
            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске чатов: {e}")

    @skill()
    async def join_chat(self, link_or_username: str) -> SkillResult:
        """
        Вступает в канал или группу.
        Принимает публичный юзернейм или закрытую пригласительную ссылку.
        """
        try:
            client = self.tg_client.client()
            target = link_or_username.strip()

            # Проверяем, является ли это приватной ссылкой-приглашением
            if "t.me/+" in target or "t.me/joinchat/" in target or target.startswith("+"):
                # Извлекаем уникальный хэш ссылки
                hash_match = re.search(r"(?:joinchat/|\+)([\w-]+)", target)
                if not hash_match:
                    return SkillResult.fail(
                        "Ошибка: Не удалось извлечь хэш из пригласительной ссылки."
                    )

                invite_hash = hash_match.group(1)
                await client(ImportChatInviteRequest(invite_hash))

            else:
                # Это публичный канал или группа
                await client(JoinChannelRequest(target))

            system_logger.info(f"Агент вступил в чат: {target}")
            return SkillResult.ok(f"Успешно вступили в чат: {target}")

        except Exception as e:
            msg = str(e)
            if "UserAlreadyParticipant" in msg or "USER_ALREADY_PARTICIPANT" in msg:
                return SkillResult.ok(f"Вы уже состоите в этом чате ({target}).")
            return SkillResult.fail(f"Ошибка при вступлении в чат: {e}")

    @skill()
    async def leave_chat(self, chat_id: int) -> SkillResult:
        """Покидает канал или группу по её числовому ID."""
        try:
            client = self.tg_client.client()

            # Получаем сущность чата (чтобы Telethon сформировал правильный запрос к API)
            entity = await client.get_input_entity(int(chat_id))

            await client(LeaveChannelRequest(entity))

            system_logger.info(f"Агент покинул чат: {chat_id}")
            return SkillResult.ok(f"Успешно покинули чат {chat_id}.")

        except ValueError:
            return SkillResult.fail(
                f"Ошибка: Некорректный ID чата ({chat_id}). Убедитесь, что передаете число."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка при выходе из чата: {e}")

    @skill()
    async def join_channel_discussion(self, channel_id: int) -> SkillResult:
        """
        Узнает ID привязанной группы для комментариев у канала и вступает в нее.
        """
        try:
            client = self.tg_client.client()
            
            # Получаем полную информацию о канале
            target_entity = await client.get_input_entity(int(channel_id))
            full_channel = await client(GetFullChannelRequest(target_entity))
            
            linked_chat_id = full_channel.full_chat.linked_chat_id
            
            if not linked_chat_id:
                return SkillResult.fail(f"Ошибка: У канала {channel_id} нет привязанной группы для обсуждений.")
            
            # Вступаем в привязанную группу
            await client(JoinChannelRequest(await client.get_input_entity(linked_chat_id)))
            
            system_logger.info(f"Агент вступил в группу обсуждения: {linked_chat_id} (для канала {channel_id})")
            return SkillResult.ok(f"Успешное вступление в группу обсуждений (ID: {linked_chat_id}).")
            
        except ValueError:
            return SkillResult.fail(f"Ошибка: Некорректный ID канала ({channel_id}).")
            
        except Exception as e:
            msg = str(e)
            if "UserAlreadyParticipant" in msg or "USER_ALREADY_PARTICIPANT" in msg:
                return SkillResult.ok("Вы уже состоите в группе обсуждений этого канала.")
            return SkillResult.fail(f"Ошибка при вступлении в обсуждение канала: {e}")
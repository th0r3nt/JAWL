import re
from datetime import timezone, timedelta
from typing import Optional

from telethon import utils
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import (
    JoinChannelRequest,
    LeaveChannelRequest,
    GetFullChannelRequest,
)
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
        """Возвращает список последних чатов (пользователи, группы, каналы). Если это форум, возвращает топики."""

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

                is_forum = getattr(dialog.entity, "forum", False)
                forum_str = ""

                if is_forum:
                    chat_type = "Forum"
                    topics = []
                    try:
                        # Получаем последние 10 топиков форума
                        async for topic in client.iter_forum_topics(dialog.entity, limit=10):
                            t_unread = (
                                f" ({topic.unread_count} непр.)"
                                if getattr(topic, "unread_count", 0) > 0
                                else ""
                            )
                            topics.append(
                                f"      ↳ Топик '{topic.title}' (ID: {topic.id}){t_unread}"
                            )
                    except Exception:
                        pass

                    if topics:
                        forum_str = "\n" + "\n".join(topics)

                chats.append(
                    f"- {chat_type} | ID: `{dialog.id}` | Название: {dialog.name}{unread}{forum_str}"
                )

            if not chats:
                return SkillResult.ok("Список чатов пуст.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка чатов: {e}")

    @skill()
    async def get_unread_chats(self) -> SkillResult:
        """Возвращает список чатов, в которых есть непрочитанные сообщения (включая топики форумов)."""

        try:
            client = self.tg_client.client()
            chats = []

            # Ограничиваем скан первыми 50 диалогами, чтобы не нагружать API
            async for dialog in client.iter_dialogs(limit=50):
                if dialog.unread_count > 0:
                    chat_type = (
                        "User" if dialog.is_user else "Group" if dialog.is_group else "Channel"
                    )

                    is_forum = getattr(dialog.entity, "forum", False)
                    forum_str = ""

                    if is_forum:
                        chat_type = "Forum"
                        topics = []
                        try:
                            # В форумах выводим только те топики, где реально есть непрочитанные
                            async for topic in client.iter_forum_topics(dialog.entity):
                                unread = getattr(topic, "unread_count", 0)
                                if unread > 0:
                                    topics.append(
                                        f"      ↳ Топик '{topic.title}' (ID: {topic.id}) [{unread} непр.]"
                                    )
                        except Exception:
                            pass

                        if topics:
                            forum_str = "\n" + "\n".join(topics)

                    chats.append(
                        f"- {chat_type} | ID: `{dialog.id}` | Название: **{dialog.name}** | Непрочитанных: {dialog.unread_count}{forum_str}"
                    )

            if not chats:
                return SkillResult.ok("Нет непрочитанных сообщений.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске непрочитанных чатов: {e}")

    @skill()
    async def read_chat(
        self, chat_id: int, limit: int = 10, topic_id: Optional[int] = None
    ) -> SkillResult:
        """
        Читает историю указанного чата.
        Если чат является форумом, следует передать topic_id, чтобы прочитать конкретный топик.
        """

        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(int(chat_id))

            try:
                await client.send_read_acknowledge(target_entity)
            except Exception:
                pass

            messages = []

            # Поддержка топиков (для Telethon топик — это просто reply_to_msg_id корневого сообщения)
            kwargs = {"limit": limit}
            if topic_id:
                kwargs["reply_to"] = int(topic_id)

            async for msg in client.iter_messages(target_entity, **kwargs):
                # 1. Отправитель
                sender_name = "Unknown"
                if msg.sender:
                    sender_name = utils.get_display_name(msg.sender)

                # 2. Формирование контента
                content_parts = []
                if msg.action:
                    content_parts.append("[Системное сообщение]")
                if msg.media:
                    if msg.photo:
                        content_parts.append("[Фотография]")
                    elif msg.sticker:
                        # Достаем эмодзи стикера для лучшего контекста агента
                        emoji = msg.file.emoji if (hasattr(msg, 'file') and msg.file) else ""
                        sticker_text = f"[Стикер {emoji}]" if emoji else "[Стикер]"
                        content_parts.append(sticker_text)
                    elif getattr(msg, "gif", None):
                        content_parts.append("[GIF]")
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
                # Если мы читаем топик, то игнорируем системный reply_to на сам topic_id,
                # чтобы не спамить агенту "В ответ на сообщение..." в каждом сообщении.
                is_actual_reply = msg.is_reply and msg.reply_to_msg_id
                if is_actual_reply and str(msg.reply_to_msg_id) != str(topic_id):
                    try:
                        orig_msg = await msg.get_reply_message()
                        orig_sender = (
                            utils.get_display_name(orig_msg.sender)
                            if (orig_msg and orig_msg.sender)
                            else "Unknown"
                        )
                        reply_context = f"\n  ↳ (В ответ на сообщение ID {msg.reply_to_msg_id} от {orig_sender})"
                    except Exception:
                        reply_context = (
                            f"\n  ↳ (В ответ на сообщение ID {msg.reply_to_msg_id})"
                        )

                # 4. Сборка итоговой строки
                tz = timezone(timedelta(hours=self.tg_client.timezone))
                time_str = msg.date.astimezone(tz).strftime("%Y-%m-%d %H:%M")
                messages.append(
                    f"[{time_str}][ID: {msg.id}] {sender_name}: {final_text}{reply_context}"
                )

            if not messages:
                if topic_id:
                    return SkillResult.ok(
                        "В этом топике нет сообщений (или он не существует)."
                    )
                return SkillResult.ok("В этом чате нет сообщений.")

            # Разворачиваем, чтобы диалог читался сверху вниз (старые -> новые)
            messages.reverse()
            return SkillResult.ok("\n\n".join(messages))

        except ValueError:
            return SkillResult.fail(f"Ошибка: Некорректный ID чата ({chat_id}).")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении чата {chat_id}: {e}")

    @skill()
    async def mark_as_read(self, chat_id: int) -> SkillResult:
        """Помечает все сообщения в чате как прочитанные."""

        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(int(chat_id))
            await client.send_read_acknowledge(target_entity)
            return SkillResult.ok(f"Чат {chat_id} успешно помечен как прочитанный.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при пометке чата {chat_id} как прочитанного: {e}")

    @skill()
    async def search_public_chats(self, query: str, limit: int = 5) -> SkillResult:
        """Ищет публичные группы и каналы в глобальном поиске Telegram по запросу."""

        try:
            client = self.tg_client.client()
            result = await client(SearchRequest(q=query, limit=limit))
            chats = []
            for chat in result.chats:
                chat_type = "Channel" if getattr(chat, "broadcast", False) else "Group"
                username = f"@{chat.username}" if getattr(chat, "username", None) else "Нет"
                chats.append(
                    f"- {chat_type} | ID: `{chat.id}` | Название: {chat.title} | Юзернейм: {username}"
                )
            if not chats:
                return SkillResult.ok(f"По глобальному запросу '{query}' ничего не найдено.")
            return SkillResult.ok("\n".join(chats))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске чатов: {e}")

    @skill()
    async def join_chat(self, link_or_username: str) -> SkillResult:
        """Вступает в канал или группу по юзернейму или ссылке."""

        try:
            client = self.tg_client.client()
            target = link_or_username.strip()

            if "t.me/+" in target or "t.me/joinchat/" in target or target.startswith("+"):
                hash_match = re.search(r"(?:joinchat/|\+)([\w-]+)", target)
                if not hash_match:
                    return SkillResult.fail(
                        "Ошибка: Не удалось извлечь хэш из пригласительной ссылки."
                    )
                await client(ImportChatInviteRequest(hash_match.group(1)))
            else:
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
            entity = await client.get_input_entity(int(chat_id))
            await client(LeaveChannelRequest(entity))
            system_logger.info(f"Агент покинул чат: {chat_id}")
            return SkillResult.ok(f"Успешно покинули чат {chat_id}.")
        except ValueError:
            return SkillResult.fail(
                "Ошибка: Некорректный ID чата. Убедитесь, что передаете число."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка при выходе из чата: {e}")

    @skill()
    async def join_channel_discussion(self, channel_id: int) -> SkillResult:
        """Узнает ID привязанной группы для комментариев у канала и вступает в нее."""

        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(int(channel_id))
            full_channel = await client(GetFullChannelRequest(target_entity))
            linked_chat_id = full_channel.full_chat.linked_chat_id

            if not linked_chat_id:
                return SkillResult.fail(
                    f"Ошибка: У канала {channel_id} нет привязанной группы для обсуждений."
                )

            await client(JoinChannelRequest(await client.get_input_entity(linked_chat_id)))
            system_logger.info(
                f"[Telegram Telethon] Успешное вступление в группу обсуждений (ID: {linked_chat_id})"
            )
            return SkillResult.ok(
                f"Успешное вступление в группу обсуждений (ID: {linked_chat_id})."
            )
        
        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID канала.")
        
        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                return SkillResult.ok("Вы уже состоите в группе обсуждений этого канала.")
            return SkillResult.fail(f"Ошибка при вступлении в обсуждение: {e}")

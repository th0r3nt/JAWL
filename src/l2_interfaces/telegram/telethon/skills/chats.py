import re
from typing import Optional, Union, Tuple, Any

from telethon import utils
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import (
    JoinChannelRequest,
    LeaveChannelRequest,
    GetFullChannelRequest,
    InviteToChannelRequest,
)
from telethon.tl.functions.messages import ImportChatInviteRequest

from src.utils.logger import system_logger
from src.utils.dtime import format_datetime

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill


class TelethonChats:
    """
    Навыки для работы со списком чатов, чтения сообщений и управления участием.
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    def _parse_entity(self, entity_id: Union[int, str]) -> Union[int, str]:
        """Утилитный метод для преобразования строковых ID в числа."""
        try:
            return int(entity_id)
        except ValueError:
            return str(entity_id).strip()

    # =================================================================
    # Хелперы для парсинга сообщений (SRP)
    # =================================================================

    def _get_sender_name(self, msg: Any) -> str:
        """Определяет имя отправителя сообщения."""

        if msg.sender:
            name = utils.get_display_name(msg.sender)
            return f"{name} (ID: {msg.sender_id})" if msg.sender_id else name
        elif msg.sender_id:
            return f"Unknown (ID: {msg.sender_id})"
        return "Unknown"

    def _determine_reply(
        self, msg: Any, topic_id: Optional[int]
    ) -> Tuple[bool, Optional[int]]:
        """
        Определяет, является ли сообщение реальным ответом на другое сообщение.
        Отсекает баги форумов.
        """

        if not msg.reply_to:
            return False, None

        reply_id = None
        is_actual_reply = False

        if getattr(msg.reply_to, "forum_topic", False):
            top_id = getattr(msg.reply_to, "reply_to_top_id", None)
            if top_id and msg.reply_to.reply_to_msg_id != top_id:
                is_actual_reply = True
                reply_id = msg.reply_to.reply_to_msg_id
        else:
            is_actual_reply = True
            reply_id = msg.reply_to.reply_to_msg_id

        # Если читаем конкретный топик, первый пост ссылается сам на себя - игнорируем
        if is_actual_reply and str(reply_id) == str(topic_id):
            is_actual_reply = False

        return is_actual_reply, reply_id

    def _parse_media(self, msg: Any) -> str:
        """Анализирует наличие медиа-вложений или системных действий."""

        if msg.action:
            return "[Системное сообщение]"
        if not msg.media:
            return ""

        if msg.photo:
            return "[Фотография]"

        if msg.sticker:
            emoji = msg.file.emoji if (hasattr(msg, "file") and msg.file) else ""
            return f"[Стикер {emoji}]" if emoji else "[Стикер]"

        if getattr(msg, "gif", None):
            return "[GIF]"

        if msg.voice:
            return "[Голосовое сообщение]"

        if msg.video or msg.video_note:
            return "[Видео]"

        if msg.document:
            return "[Файл]"

        if msg.poll:
            return "[Опрос]"

        return "[Медиа]"

    async def _parse_forward(self, msg: Any) -> str:
        """Получает инфу о пересланном сообщении."""

        if not msg.fwd_from:
            return ""

        try:
            fwd_sender = await msg.get_forward_sender()
            if fwd_sender:
                return f"\n  ↳[Переслано от: {utils.get_display_name(fwd_sender)}]"
            elif msg.fwd_from.from_name:
                return f"\n  ↳[Переслано от: {msg.fwd_from.from_name}]"

        except Exception:
            pass

        return "\n  ↳ [Переслано]"

    async def _parse_reply(
        self, client: Any, target_entity: Any, is_reply: bool, reply_id: Optional[int]
    ) -> str:
        """Формирует строку-контекст ответа (кто и кому ответил)."""

        if not is_reply or not reply_id:
            return ""

        try:
            orig_msg = await client.get_messages(target_entity, ids=reply_id)
            if orig_msg and orig_msg.sender:
                orig_name = utils.get_display_name(orig_msg.sender)
                orig_sender = (
                    f"{orig_name} (ID: {orig_msg.sender_id})"
                    if orig_msg.sender_id
                    else orig_name
                )

            elif orig_msg and orig_msg.sender_id:
                orig_sender = f"Unknown (ID: {orig_msg.sender_id})"

            else:
                orig_sender = "Unknown"

            return f"\n  ↳ (В ответ на сообщение ID {reply_id} от {orig_sender})"

        except Exception:
            return f"\n  ↳ (В ответ на сообщение ID {reply_id})"

    async def _parse_reactions(self, client: Any, msg: Any) -> str:
        """Стягивает информацию о реакциях и том, кто их поставил."""

        if not getattr(msg, "reactions", None):
            return ""

        r_list = []

        if getattr(msg.reactions, "recent_reactions", None):
            for r in msg.reactions.recent_reactions:
                emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                try:
                    peer = await client.get_entity(r.peer_id)
                    name = utils.get_display_name(peer) or "Unknown"
                    r_list.append(f"{emo} от {name}")

                except Exception:
                    r_list.append(f"{emo}")

        elif getattr(msg.reactions, "results", None):
            for r in msg.reactions.results:
                emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                r_list.append(f"{emo} x{r.count}")

        return f"\n  ↳[Реакции: {', '.join(r_list)}]" if r_list else ""

    def _parse_buttons(self, msg: Any) -> str:
        """Парсит inline-клавиатуру, если она есть."""

        if not getattr(msg, "buttons", None):
            return ""

        btn_texts = [f"[{btn.text}]" for row in msg.buttons for btn in row if btn.text]
        return f"\n  ↳[Кнопки: {', '.join(btn_texts)}]" if btn_texts else ""

    # =================================================================
    # Навыки
    # =================================================================

    @skill()
    async def get_chats(self, limit: int = 10) -> SkillResult:
        """
        Возвращает список последних чатов (пользователи, группы, каналы).
        Если это форум, возвращает топики.
        """

        try:
            client = self.tg_client.client()
            chats = []

            async for dialog in client.iter_dialogs(limit=limit):
                chat_type = (
                    "User" if dialog.is_user else "Group" if dialog.is_group else "Channel"
                )
                unread = (
                    f"[Непрочитанных: {dialog.unread_count}]"
                    if dialog.unread_count > 0
                    else ""
                )

                forum_str = ""
                if getattr(dialog.entity, "forum", False):
                    chat_type = "Forum"
                    topics = []
                    try:
                        async for topic in client.iter_forum_topics(dialog.entity, limit=10):
                            t_unread = (
                                f" ({topic.unread_count} непр.)"
                                if getattr(topic, "unread_count", 0) > 0
                                else ""
                            )
                            topics.append(
                                f"      ↳ Топик '{topic.title}' (ID: {topic.id}){t_unread}"
                            )
                    except Exception as e:
                        system_logger.error(
                            f"[TelethonChats] Ошибка iter_forum_topics в get_chats: {e}"
                        )

                    # Если топиков нет, но сообщения висят - значит они в дефолтном General
                    if not topics and dialog.unread_count > 0:
                        topics.append(
                            f"      ↳ General / Общий топик ({dialog.unread_count} непр.)"
                        )

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
    async def get_unread_chats(self, limit: int = 20) -> SkillResult:
        """
        Возвращает список чатов, в которых есть непрочитанные сообщения.
        """
        try:
            client = self.tg_client.client()
            chats = []

            async for dialog in client.iter_dialogs(limit=limit):
                if dialog.unread_count > 0:
                    chat_type = (
                        "User" if dialog.is_user else "Group" if dialog.is_group else "Channel"
                    )
                    forum_str = ""

                    if getattr(dialog.entity, "forum", False):
                        chat_type = "Forum"
                        topics = []
                        try:
                            async for topic in client.iter_forum_topics(dialog.entity):
                                unread = getattr(topic, "unread_count", 0)
                                if unread > 0:
                                    topics.append(
                                        f"      ↳ Топик '{topic.title}' (ID: {topic.id}) [{unread} непр.]"
                                    )
                        except Exception as e:
                            system_logger.error(
                                f"[TelethonChats] Ошибка iter_forum_topics в get_unread_chats: {e}"
                            )

                        # Fallback для General топика
                        if not topics:
                            topics.append(
                                f"      ↳ General / Другие топики [{dialog.unread_count} непр.]"
                            )

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
        self, chat_id: Union[int, str], limit: int = 10, topic_id: Optional[int] = None
    ) -> SkillResult:
        """
        Читает историю указанного чата.
        Если чат является форумом, следует передать topic_id, чтобы прочитать конкретный топик.
        """
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(self._parse_entity(chat_id))

            try:
                kwargs_ack = {}
                if topic_id:
                    kwargs_ack["reply_to"] = int(topic_id)
                await client.send_read_acknowledge(target_entity, **kwargs_ack)
            except Exception:
                pass

            messages = []
            kwargs = {"limit": limit}
            if topic_id:
                kwargs["reply_to"] = int(topic_id)

            async for msg in client.iter_messages(target_entity, **kwargs):

                # Получаем имя сообщения
                sender_name = self._get_sender_name(msg)

                # Проверяем наличие reply
                is_reply, reply_id = self._determine_reply(msg, topic_id)

                # Собираем остальные части сообщения
                parts = [
                    self._parse_media(msg),
                    msg.text or "",
                    await self._parse_forward(msg),
                    await self._parse_reply(client, target_entity, is_reply, reply_id),
                    await self._parse_reactions(client, msg),
                    self._parse_buttons(msg),
                ]

                # Фильтруем пустые элементы и склеиваем
                final_text = " ".join(filter(bool, parts)) or "[Пустое сообщение]"
                time_str = format_datetime(
                    msg.date, self.tg_client.timezone, fmt="%Y-%m-%d %H:%M"
                )

                messages.append(f"[{time_str}] [ID: {msg.id}] {sender_name}: {final_text}")

            if not messages:
                return SkillResult.ok(
                    "В этом топике нет сообщений."
                    if topic_id
                    else "В этом чате нет сообщений."
                )

            messages.reverse()
            return SkillResult.ok("\n\n".join(messages))

        except ValueError:
            return SkillResult.fail(f"Ошибка: Некорректный ID чата ({chat_id}).")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении чата {chat_id}: {e}")

    @skill()
    async def mark_as_read(
        self, chat_id: Union[int, str], topic_id: Optional[int] = None
    ) -> SkillResult:
        """Помечает все сообщения в чате (или конкретном топике) как прочитанные."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(self._parse_entity(chat_id))

            if getattr(target_entity, "forum", False) and not topic_id:
                # Если это форум и топик не указан - нужно перебрать все топики
                try:
                    async for topic in client.iter_forum_topics(target_entity):
                        if getattr(topic, "unread_count", 0) > 0:
                            await client.send_read_acknowledge(
                                target_entity, reply_to=topic.id
                            )

                except Exception as e:
                    system_logger.error(f"[TelethonChats] Ошибка при очистке топиков: {e}")

                # Плюс помечаем основную ветку (General)
                await client.send_read_acknowledge(target_entity)
            else:
                kwargs = {}
                if topic_id:
                    kwargs["reply_to"] = int(topic_id)
                await client.send_read_acknowledge(target_entity, **kwargs)

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

            return SkillResult.ok(f"Успешно вступили в чат: {target}")

        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                return SkillResult.ok(f"Вы уже состоите в этом чате ({target}).")

            return SkillResult.fail(f"Ошибка при вступлении в чат: {e}")

    @skill()
    async def leave_chat(self, chat_id: Union[int, str]) -> SkillResult:
        """Покидает канал или группу."""

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(self._parse_entity(chat_id))
            await client(LeaveChannelRequest(entity))

            # system_logger.info(f"[Telegram Telethon] Агент покинул чат: {chat_id}")
            return SkillResult.ok(f"Успешно покинули чат {chat_id}.")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный формат ID чата.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при выходе из чата: {e}")

    @skill()
    async def join_channel_discussion(self, channel_id: Union[int, str]) -> SkillResult:
        """Узнает ID привязанной группы для комментариев у канала и вступает в нее."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(self._parse_entity(channel_id))
            full_channel = await client(GetFullChannelRequest(target_entity))
            linked_chat_id = full_channel.full_chat.linked_chat_id

            if not linked_chat_id:
                return SkillResult.fail(
                    f"Ошибка: У канала {channel_id} нет привязанной группы для обсуждений."
                )

            await client(JoinChannelRequest(await client.get_input_entity(linked_chat_id)))
            # system_logger.info(
            #     f"[Telegram Telethon] Успешное вступление в группу обсуждений (ID: {linked_chat_id})"
            # )

            return SkillResult.ok(
                f"Успешное вступление в группу обсуждений (ID: {linked_chat_id})."
            )

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID канала.")
        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                return SkillResult.ok("Вы уже состоите в группе обсуждений этого канала.")
            return SkillResult.fail(f"Ошибка при вступлении в обсуждение: {e}")

    @skill()
    async def invite_to_chat(
        self, chat_id: Union[int, str], users: list[Union[int, str]]
    ) -> SkillResult:
        """
        Приглашает одного или нескольких пользователей в группу или канал.
        users: Список из числовых ID или юзернеймов (@username).
        """
        if not users:
            return SkillResult.fail("Ошибка: Список пользователей пуст.")

        try:
            client = self.tg_client.client()
            chat_entity = await client.get_input_entity(self._parse_entity(chat_id))

            user_entities = []
            for u in users:
                try:
                    user_entities.append(await client.get_input_entity(self._parse_entity(u)))
                except ValueError:
                    return SkillResult.fail(
                        f"Ошибка: Пользователь '{u}' не найден. Проверьте правильность юзернейма."
                    )

            await client(InviteToChannelRequest(channel=chat_entity, users=user_entities))

            # system_logger.info(
            #     f"[Telegram Telethon] Пользователи {users} приглашены в чат {chat_id}"
            # )
            return SkillResult.ok(f"Успешно. Пользователи {users} приглашены в чат {chat_id}.")

        except Exception as e:
            msg = str(e)

            if "USER_PRIVACY_RESTRICTED" in msg:
                return SkillResult.fail(
                    "Ошибка: Настройки приватности ограничивают добавление кого-то из списка."
                )

            if "CHAT_ADMIN_REQUIRED" in msg:
                return SkillResult.fail("Ошибка: Нет прав на приглашение в этот чат.")

            if "USER_ALREADY_PARTICIPANT" in msg:
                return SkillResult.ok(
                    "Запрос выполнен, некоторые (или все) пользователи уже состоят в чате."
                )

            if "USER_NOT_MUTUAL_CONTACT" in msg:
                return SkillResult.fail(
                    "Ошибка: Пользователя можно пригласить только если вы взаимные контакты."
                )

            return SkillResult.fail(f"Ошибка при инвайтинге: {e}")

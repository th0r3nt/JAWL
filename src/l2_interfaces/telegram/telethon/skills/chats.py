import re
from typing import Optional, Union

from telethon import utils
from telethon.tl.functions.contacts import SearchRequest, AddContactRequest
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
                    f"[Непрочитанных: {dialog.unread_count}]"
                    if dialog.unread_count > 0
                    else ""
                )

                is_forum = getattr(dialog.entity, "forum", False)
                forum_str = ""

                if is_forum:
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
                await client.send_read_acknowledge(target_entity)
            except Exception:
                pass

            messages = []
            kwargs = {"limit": limit}
            if topic_id:
                kwargs["reply_to"] = int(topic_id)

            async for msg in client.iter_messages(target_entity, **kwargs):
                sender_name = "Unknown"
                if msg.sender:
                    name = utils.get_display_name(msg.sender)
                    sender_name = f"{name} (ID: {msg.sender_id})" if msg.sender_id else name
                elif msg.sender_id:
                    sender_name = f"Unknown (ID: {msg.sender_id})"

                # Логика определения реальных ответов (отсечение костылей Telegram-форумов)
                is_actual_reply = False
                reply_id = None

                if msg.reply_to:
                    if getattr(msg.reply_to, "forum_topic", False):
                        # В топиках форума обычные сообщения имеют reply_to_msg_id == ID топика
                        top_id = getattr(msg.reply_to, "reply_to_top_id", None)
                        # Если top_id существует, и reply_to_msg_id не равен top_id, значит это реальный ответ
                        if top_id and msg.reply_to.reply_to_msg_id != top_id:
                            is_actual_reply = True
                            reply_id = msg.reply_to.reply_to_msg_id
                    else:
                        # В обычных группах и ЛС всё просто
                        is_actual_reply = True
                        reply_id = msg.reply_to.reply_to_msg_id

                # Если мы принудительно читаем историю конкретного топика (иногда первый пост ссылается сам на себя)
                if is_actual_reply and str(reply_id) == str(topic_id):
                    is_actual_reply = False

                # =================================================================
                # МЕДИА

                content_parts = []

                if msg.action:
                    content_parts.append("[Системное сообщение]")

                if msg.media:
                    if msg.photo:
                        content_parts.append("[Фотография]")

                    elif msg.sticker:
                        emoji = msg.file.emoji if (hasattr(msg, "file") and msg.file) else ""
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

                # =================================================================
                # ПЕРЕСЛАННЫЕ СООБЩЕНИЯ

                forward_context = ""

                if msg.fwd_from:
                    try:
                        fwd_sender = await msg.get_forward_sender()
                        if fwd_sender:
                            fwd_name = utils.get_display_name(fwd_sender)
                            forward_context = f"\n  ↳[Переслано от: {fwd_name}]"
                        elif msg.fwd_from.from_name:
                            forward_context = f"\n  ↳[Переслано от: {msg.fwd_from.from_name}]"
                        else:
                            forward_context = "\n  ↳ [Переслано]"
                    except Exception:
                        forward_context = "\n  ↳ [Переслано]"

                # =================================================================
                # REPLY

                reply_context = ""

                if is_actual_reply and reply_id:
                    try:
                        # Запрашиваем оригинальное сообщение, на которое был дан ответ
                        orig_msg = await client.get_messages(target_entity, ids=reply_id)
                        orig_sender = "Unknown"
                        if orig_msg and orig_msg.sender:
                            orig_name = utils.get_display_name(orig_msg.sender)
                            orig_sender = (
                                f"{orig_name} (ID: {orig_msg.sender_id})"
                                if orig_msg.sender_id
                                else orig_name
                            )
                        elif orig_msg and orig_msg.sender_id:
                            orig_sender = f"Unknown (ID: {orig_msg.sender_id})"

                        reply_context = (
                            f"\n  ↳ (В ответ на сообщение ID {reply_id} от {orig_sender})"
                        )
                    except Exception:
                        reply_context = f"\n  ↳ (В ответ на сообщение ID {reply_id})"

                # =================================================================
                # РЕАКЦИИ

                reaction_context = ""

                if getattr(msg, "reactions", None):
                    r_list = []

                    # Пытаемся достать детализацию: кто именно поставил реакцию (recent_reactions)
                    if getattr(msg.reactions, "recent_reactions", None):
                        for r in msg.reactions.recent_reactions:
                            emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                            try:
                                # Берем имя пользователя из локального кэша Telethon (это быстро)
                                peer = await client.get_entity(r.peer_id)
                                name = utils.get_display_name(peer) or "Unknown"
                                r_list.append(f"{emo} от {name}")
                            except Exception:
                                # Если юзера нет в кэше, просто выводим эмодзи
                                r_list.append(f"{emo}")

                    # Если детализации нет, выводим общие счетчики как фоллбэк
                    elif getattr(msg.reactions, "results", None):
                        for r in msg.reactions.results:
                            emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                            r_list.append(f"{emo} x{r.count}")

                    if r_list:
                        reaction_context = f"\n  ↳[Реакции: {', '.join(r_list)}]"

                # =================================================================
                # INLINE КНОПКИ

                buttons_context = ""

                if getattr(msg, "buttons", None):
                    btn_texts = []
                    for row in msg.buttons:
                        for btn in row:
                            if btn.text:
                                btn_texts.append(f"[{btn.text}]")
                    if btn_texts:
                        buttons_context = f"\n  ↳[Кнопки: {', '.join(btn_texts)}]"

                # =================================================================
                # СКЛЕИВАНИЕ СООБЩЕНИЯ

                final_text = " ".join(content_parts) if content_parts else "[Пустое сообщение]"

                time_str = format_datetime(
                    msg.date, self.tg_client.timezone, fmt="%Y-%m-%d %H:%M"
                )

                messages.append(
                    f"[{time_str}] [ID: {msg.id}] {sender_name}: {final_text}{forward_context}{reply_context}{reaction_context}{buttons_context}"  # Помогите
                )

            if not messages:
                if topic_id:
                    return SkillResult.ok(
                        "В этом топике нет сообщений (или он не существует)."
                    )
                return SkillResult.ok("В этом чате нет сообщений.")

            messages.reverse()
            return SkillResult.ok("\n\n".join(messages))

        except ValueError:
            return SkillResult.fail(f"Ошибка: Некорректный ID чата ({chat_id}).")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении чата {chat_id}: {e}")

    @skill()
    async def mark_as_read(self, chat_id: Union[int, str]) -> SkillResult:
        """Помечает все сообщения в чате как прочитанные."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(self._parse_entity(chat_id))
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

            # И так логгируется в Agent Action Result
            # system_logger.info(f"[Telegram Telethon] Агент вступил в чат: {target}")
            return SkillResult.ok(f"Успешно вступили в чат: {target}")

        except Exception as e:
            msg = str(e)
            if "USER_ALREADY_PARTICIPANT" in msg:
                return SkillResult.ok(f"Вы уже состоите в этом чате ({target}).")
            return SkillResult.fail(f"Ошибка при вступлении в чат: {e}")

    @skill()
    async def leave_chat(self, chat_id: Union[int, str]) -> SkillResult:
        """Покидает канал или группу."""
        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(self._parse_entity(chat_id))
            await client(LeaveChannelRequest(entity))
            system_logger.info(f"[Telegram Telethon] Агент покинул чат: {chat_id}")
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

            system_logger.info(
                f"[Telegram Telethon] Пользователи {users} приглашены в чат {chat_id}"
            )
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

    @skill()
    async def add_contact(
        self, user_id: Union[int, str], first_name: str, last_name: str = ""
    ) -> SkillResult:
        """
        Добавляет пользователя в контакты Telegram.
        """
        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(self._parse_entity(user_id))

            # Telethon позволяет добавить контакт без номера телефона,
            # если мы укажем пустую строку и передадим InputUser объект (target_entity)
            await client(
                AddContactRequest(
                    id=target_entity,
                    first_name=first_name,
                    last_name=last_name,
                    phone="",
                    add_phone_privacy_exception=False,
                )
            )

            name_str = f"{first_name} {last_name}".strip()
            system_logger.info(
                f"[Telegram Telethon] Пользователь {user_id} добавлен в контакты как '{name_str}'"
            )
            return SkillResult.ok(
                f"Успешно. Пользователь {user_id} добавлен в контакты как '{name_str}'."
            )

        except ValueError:
            return SkillResult.fail(
                f"Ошибка: Пользователь '{user_id}' не найден. Проверьте правильность ID или юзернейма."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка при добавлении в контакты: {e}")

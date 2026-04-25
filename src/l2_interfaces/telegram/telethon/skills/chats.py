import re
from typing import Optional, Union, Any

from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import (
    JoinChannelRequest,
    LeaveChannelRequest,
    GetFullChannelRequest,
    InviteToChannelRequest,
)
from telethon.tl.functions.messages import (
    ImportChatInviteRequest,
    GetPeerDialogsRequest,
    ReadMentionsRequest,
    GetFullChatRequest,
)

from src.utils.logger import system_logger
from src.utils._tools import parse_int_or_str

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.utils._message_parser import TelethonMessageParser
from src.l3_agent.skills.registry import SkillResult, skill


# Безопасный импорт для поддержки старых версий Telethon
try:
    from telethon.tl.functions.channels import GetForumTopicsRequest
except ImportError:
    GetForumTopicsRequest = None

try:
    from telethon.tl.functions.messages import ReadReactionsRequest
except ImportError:
    ReadReactionsRequest = None


class TelethonChats:
    """
    Навыки для работы со списком чатов, чтения сообщений и управления участием.
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

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

            # Получаем общее количество диалогов
            total_dialogs = 0
            try:
                d_info = await client.get_dialogs(limit=0)
                total_dialogs = getattr(d_info, "total", 0)
            except Exception:
                pass

            async for dialog in client.iter_dialogs(limit=limit):
                chat_type = (
                    "User" if dialog.is_user else "Group" if dialog.is_group else "Channel"
                )
                unread = f" [UNREAD: {dialog.unread_count}]" if dialog.unread_count > 0 else ""

                forum_str = ""
                if getattr(dialog.entity, "forum", False):
                    chat_type = "Forum"
                    topics_list = []
                    try:
                        # Получаем топики через безопасный хелпер
                        topics_data = await self._get_topics(client, dialog.entity, limit=10)
                        for topic in topics_data:
                            t_unread = (
                                f" (UNREAD: {topic.unread_count})"
                                if getattr(topic, "unread_count", 0) > 0
                                else ""
                            )
                            topics_list.append(
                                f"      ↳ Топик '{getattr(topic, 'title', 'Unknown')}' (ID: {topic.id}){t_unread}"
                            )
                    except Exception as e:
                        system_logger.error(
                            f"[TelethonChats] Ошибка при получении топиков в get_chats: {e}"
                        )

                    # Если топиков нет, но сообщения висят - значит они в дефолтном General
                    if not topics_list and dialog.unread_count > 0:
                        topics_list.append(
                            f"      ↳ General / Общий топик (UNREAD: {dialog.unread_count})"
                        )

                    if topics_list:
                        forum_str = "\n" + "\n".join(topics_list)

                chats.append(
                    f"- {chat_type} | ID: `{dialog.id}` | Название: {dialog.name}{unread}{forum_str}"
                )

            if not chats:
                return SkillResult.ok("Список чатов пуст.")

            res_str = "\n".join(chats)

            # Добавляем плашку о скрытых диалогах, если они есть
            if total_dialogs > len(chats):
                hidden = total_dialogs - len(chats)
                res_str += f"\n\n...и еще {hidden} чатов скрыто. Для просмотра - увеличить параметр limit, чтобы загрузить больше."

            return SkillResult.ok(res_str)

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
                        topics_list = []
                        try:
                            topics_data = await self._get_topics(
                                client, dialog.entity, limit=100
                            )
                            for topic in topics_data:
                                unread = getattr(topic, "unread_count", 0)
                                if unread > 0:
                                    topics_list.append(
                                        f"      ↳ Топик '{getattr(topic, 'title', 'Unknown')}' (ID: {topic.id}) [UNREAD: {unread}]"
                                    )
                        except Exception as e:
                            system_logger.error(
                                f"[TelethonChats] Ошибка при получении топиков в get_unread_chats: {e}"
                            )

                        # Fallback для General топика
                        if not topics_list:
                            topics_list.append(
                                f"      ↳ General / Другие топики [UNREAD: {dialog.unread_count}]"
                            )

                        forum_str = "\n" + "\n".join(topics_list)

                    chats.append(
                        f"- {chat_type} | ID: `{dialog.id}` | Название: **{dialog.name}** | UNREAD: {dialog.unread_count}{forum_str}"
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
        Читает историю указанного чата (не помечая сообщения прочитанными).
        """
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(parse_int_or_str(chat_id))

            # ВЫРЕЗАНО: await self._mark_chat_read(client, target_entity, topic_id)

            read_outbox_max_id = 0
            try:
                peer_dialogs = await client(GetPeerDialogsRequest(peers=[target_entity]))
                if peer_dialogs and peer_dialogs.dialogs:
                    read_outbox_max_id = peer_dialogs.dialogs[0].read_outbox_max_id
            except Exception:
                pass

            messages = []
            kwargs = {"limit": limit}
            if topic_id:
                kwargs["reply_to"] = int(topic_id)

            async for msg in client.iter_messages(target_entity, **kwargs):
                formatted = await TelethonMessageParser.build_string(
                    client=client,
                    target_entity=target_entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    topic_id=topic_id,
                    read_outbox_max_id=read_outbox_max_id,
                )
                messages.append(formatted)

            draft_text = ""
            try:
                drafts = await client.get_drafts()
                for d in drafts:
                    if getattr(d.entity, "id", None) == target_entity.id:
                        if topic_id:
                            d_topic_id = getattr(d, "reply_to_msg_id", None)
                            if d_topic_id != int(topic_id):
                                continue

                        if d.text:
                            draft_text = (
                                f"\n\n[Черновик (Неотправленное сообщение)]:\n{d.text}"
                            )
                        break
            except Exception as e:
                system_logger.debug(f"[TelethonChats] Ошибка при получении черновика: {e}")

            if not messages:
                base_msg = (
                    "В этом топике нет сообщений."
                    if topic_id
                    else "В этом чате нет сообщений."
                )
                return SkillResult.ok(base_msg + draft_text)

            messages.reverse()
            return SkillResult.ok("\n\n".join(messages) + draft_text)

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
            target_entity = await client.get_entity(parse_int_or_str(chat_id))

            if getattr(target_entity, "forum", False) and not topic_id:
                # Если это форум и топик не указан - нужно перебрать все топики
                try:
                    topics_data = await self._get_topics(client, target_entity, limit=100)
                    for topic in topics_data:
                        if getattr(topic, "unread_count", 0) > 0:
                            await self._mark_chat_read(client, target_entity, topic.id)

                except Exception as e:
                    system_logger.error(f"[TelethonChats] Ошибка при очистке топиков: {e}")

                # Плюс помечаем основную ветку (General)
                await self._mark_chat_read(client, target_entity)
            else:
                await self._mark_chat_read(client, target_entity, topic_id)

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

                # Пытаемся достать количество подписчиков
                participants = getattr(chat, "participants_count", None)
                part_str = (
                    f" | Подписчиков: {participants}" if participants is not None else ""
                )

                chats.append(
                    f"- {chat_type} | ID: `{chat.id}` | Название: {chat.title} | Юзернейм: {username}{part_str}"
                )

            if not chats:
                return SkillResult.ok(f"По глобальному запросу '{query}' ничего не найдено.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске чатов: {e}")

    @skill()
    async def get_chat_info(self, chat_id: Union[int, str]) -> SkillResult:
        """
        Получает информацию о конкретном чате (описание, кол-во участников/подписчиков).
        Можно передавать ID чата или юзернейм (@username).
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_entity(parse_int_or_str(chat_id))

            lines = [f"Информация о чате {chat_id}:"]
            lines.append(f"Название: {getattr(entity, 'title', 'Unknown')}")

            if getattr(entity, "username", None):
                lines.append(f"Юзернейм: @{entity.username}")

            # Пытаемся получить полные данные (описание и точное количество участников)
            try:
                if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False):
                    full = await client(GetFullChannelRequest(channel=entity))
                    lines.append(
                        f"Тип: {'Канал' if getattr(entity, 'broadcast', False) else 'Супергруппа'}"
                    )
                    if full.full_chat.about:
                        lines.append(f"Описание: {full.full_chat.about}")
                    lines.append(
                        f"Участников (подписчиков): {full.full_chat.participants_count}"
                    )

                elif hasattr(entity, "participants_count"):
                    # Для обычных старых групп
                    full = await client(GetFullChatRequest(chat_id=entity.id))
                    lines.append("Тип: Группа")
                    if full.full_chat.about:
                        lines.append(f"Описание: {full.full_chat.about}")
                    lines.append(f"Участников: {full.full_chat.participants_count}")

            except Exception as e:
                system_logger.debug(
                    f"[TelethonChats] Не удалось получить full_chat для {chat_id}: {e}"
                )
                # Fallback: выводим то, что есть в базовом объекте
                if (
                    hasattr(entity, "participants_count")
                    and entity.participants_count is not None
                ):
                    lines.append(f"Участников: {entity.participants_count}")

            return SkillResult.ok("\n".join(lines))

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата или юзернейм.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении информации о чате: {e}")

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
            entity = await client.get_input_entity(parse_int_or_str(chat_id))
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
            target_entity = await client.get_input_entity(parse_int_or_str(channel_id))
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
            chat_entity = await client.get_input_entity(parse_int_or_str(chat_id))

            user_entities = []
            for u in users:
                try:
                    user_entities.append(await client.get_input_entity(parse_int_or_str(u)))
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

    # ===============================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # ===============================================================

    async def _get_topics(self, client: Any, entity: Any, limit: int = 100) -> list:
        """Хелпер: получает список топиков форума через Raw API Telethon."""
        if not GetForumTopicsRequest:
            system_logger.debug(
                "[TelethonChats] GetForumTopicsRequest недоступен. Топики форумов игнорируются."
            )
            return []

        try:
            result = await client(
                GetForumTopicsRequest(
                    channel=entity,
                    q="",
                    offset_date=0,
                    offset_id=0,
                    offset_topic=0,
                    limit=limit,
                )
            )
            # Возвращаем список объектов ForumTopic
            return getattr(result, "topics", [])
        except Exception as e:
            system_logger.error(f"[TelethonChats] Ошибка _get_topics: {e}")
            return []

    async def _mark_chat_read(
        self, client: Any, target_entity: Any, topic_id: Optional[int] = None
    ):
        """Хелпер: Помечает сообщения, меншны и реакции прочитанными."""

        try:
            # 1. Читаем сами сообщения
            kwargs_ack = {}
            if topic_id:
                kwargs_ack["reply_to"] = int(topic_id)
            await client.send_read_acknowledge(target_entity, **kwargs_ack)

            # 2. Жестко гасим меншны отдельным запросом
            if topic_id:
                await client(ReadMentionsRequest(peer=target_entity, top_msg_id=int(topic_id)))
            else:
                await client(ReadMentionsRequest(peer=target_entity))

            # 3. Жестко гасим реакции
            if topic_id:
                await client(
                    ReadReactionsRequest(peer=target_entity, top_msg_id=int(topic_id))
                )
            else:
                await client(ReadReactionsRequest(peer=target_entity))

        except Exception as e:
            system_logger.debug(f"[TelethonChats] Ошибка при очистке реакций/меншнов: {e}")

"""
Слушатель событий (Events Poller) для Telethon.

Мощный оркестратор входящих данных (MTProto Updates).
Перехватывает ЛС, упоминания, системные ивенты и реакции.
Управляет MRU-кэшем диалогов, вычисляет статусы "UNREAD" и динамически подтягивает
предысторию чатов (до 50 сообщений) для создания глубокого контекста в EventBus.
"""

import time
from typing import Any, TYPE_CHECKING, Dict

from telethon import events, utils
from telethon.tl.types import UpdateMessageReactions, Channel, Chat
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest, GetPeerDialogsRequest
from telethon.errors import FloodWaitError

from src.utils._tools import truncate_text
from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

if TYPE_CHECKING:
    from src.utils.settings import TelethonConfig

from src.l0_state.interfaces.state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.utils._message_parser import TelethonMessageParser


class TelethonEvents:
    """
    Фоновый воркер-слушатель событий Telethon.
    """

    def __init__(
        self,
        tg_client: TelethonClient,
        state: TelethonState,
        event_bus: EventBus,
        config: "TelethonConfig",
    ) -> None:
        """
        Инициализирует менеджер событий.

        Args:
            tg_client (TelethonClient): Инстанс клиента.
            state (TelethonState): L0 стейт.
            event_bus (EventBus): Шина событий JAWL.
            config (TelethonConfig): Конфиг с лимитами.
        """
        
        self.tg_client = tg_client
        self.state = state
        self.bus = event_bus
        self.config = config

        # Защита от спама (rate limiter для обновления стейта)
        self._last_state_update = 0.0

        # Кэш описаний чатов. Спасает от FloodWaitError, не делая FullChatRequest на каждый чих.
        self._chat_desc_cache: Dict[int, str] = {}

    async def start(self) -> None:
        """Регистрирует хендлеры на сокете Telethon и делает первичный сбор стейта."""
        client = self.tg_client.client()
        await self._update_state(force=True)

        client.add_event_handler(
            self._on_private_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_private),
        )
        client.add_event_handler(
            self._on_group_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_group),
        )
        client.add_event_handler(
            self._on_channel_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_channel and not e.is_group),
        )
        client.add_event_handler(self._on_chat_action, events.ChatAction())
        client.add_event_handler(self._on_reaction, events.Raw())
        client.add_event_handler(self._on_outgoing_message, events.NewMessage(outgoing=True))

        system_logger.info("[Telegram Telethon] Слушатели событий успешно запущены.")

    async def stop(self) -> None:
        """Останавливает обработку событий."""
        system_logger.info("[Telegram Telethon] Слушатели событий успешно остановлены.")

    async def _update_state(self, force: bool = False) -> None:
        """
        Опрашивает список диалогов и собирает дашборд последних активных чатов.
        Автоматически определяет форумы (Topics) и подсвечивает диалоги с UNREAD.

        Args:
            force (bool): Игнорировать rate limiter (3 сек) и обновить немедленно.
        """
        now = time.time()
        if not force and now - self._last_state_update < 3:
            return

        self._last_state_update = now
        client = self.tg_client.client()

        overview_lines = []
        unread_blocks = []

        try:
            total_dialogs = 0
            try:
                d_info = await client.get_dialogs(limit=0)
                total_dialogs = getattr(d_info, "total", 0)
            except Exception:
                pass

            async for dialog in client.iter_dialogs(limit=self.state.number_of_last_chats):
                entity = dialog.entity

                # 1. Сбор метаданных (через кэш, чтобы не бить API)
                desc_str = ""
                if dialog.is_group or dialog.is_channel:
                    if entity.id not in self._chat_desc_cache:
                        try:
                            about = ""
                            if isinstance(entity, Channel):
                                full = await client(GetFullChannelRequest(channel=entity))
                                about = full.full_chat.about or ""
                            elif isinstance(entity, Chat):
                                full = await client(GetFullChatRequest(chat_id=entity.id))
                                about = full.full_chat.about or ""
                            self._chat_desc_cache[entity.id] = about.strip()
                        except FloodWaitError:
                            pass
                        except Exception:
                            self._chat_desc_cache[entity.id] = ""

                    desc = self._chat_desc_cache.get(entity.id, "")
                    if desc:
                        clean_desc = desc.replace("\n", " ")
                        desc_str = (
                            f" | Описание: {truncate_text(clean_desc, 100, '... [Обрезано]')}"
                        )

                is_public = bool(getattr(entity, "username", None))
                status_str = "Public" if is_public else "Private"
                participants = getattr(entity, "participants_count", None)
                part_str = f" | {participants} чел." if participants else ""
                unread = f" [UNREAD: {dialog.unread_count}]" if dialog.unread_count > 0 else ""

                # 2. Формирование блоков
                if dialog.is_user:
                    bot_tag = " [Bot]" if getattr(entity, "bot", False) else ""
                    overview_lines.append(
                        f"- [User] {dialog.name}{bot_tag} (ID: `{dialog.id}`){unread}"
                    )

                    if dialog.unread_count > 0:
                        fetch_limit = max(
                            2, min(dialog.unread_count, self.config.incoming_history_limit)
                        )
                        try:
                            recent_msgs = await client.get_messages(entity, limit=fetch_limit)
                            if recent_msgs:
                                block = f"[User] {dialog.name}{bot_tag} (ID: {dialog.id}) [UNREAD: {dialog.unread_count}]:"
                                block += f"\n    Last {len(recent_msgs)} messages:"
                                msg_lines = []
                                for m in reversed(recent_msgs):
                                    formatted = await TelethonMessageParser.build_string(
                                        client=client,
                                        target_entity=entity,
                                        msg=m,
                                        timezone=self.tg_client.timezone,
                                        truncate_text_flag=True,
                                    )
                                    indented = "\n".join(
                                        [f"        {line}" for line in formatted.split("\n")]
                                    )
                                    msg_lines.append(indented)
                                block += "\n\n" + "\n\n".join(msg_lines)
                                unread_blocks.append(block)
                        except Exception as e:
                            system_logger.debug(
                                f"[Telethon] Ошибка загрузки истории для {dialog.id}: {e}"
                            )

                elif dialog.is_group or dialog.is_channel:
                    chat_type = "Group" if dialog.is_group else "Channel"
                    forum_str = ""

                    if getattr(dialog.entity, "forum", False):
                        chat_type = "Forum"
                        topics_list = []
                        try:
                            topics_data = await self._get_topics(
                                client, dialog.entity, limit=10
                            )
                            for topic in topics_data:
                                t_unread = (
                                    f" (UNREAD: {topic.unread_count})"
                                    if getattr(topic, "unread_count", 0) > 0
                                    else ""
                                )
                                topics_list.append(
                                    f"      ↳ Топик '{getattr(topic, 'title', 'Unknown')}' (ID: {topic.id}){t_unread}"
                                )
                        except Exception:
                            pass

                        if not topics_list and dialog.unread_count > 0:
                            topics_list.append(
                                f"      ↳ General / Общий топик (UNREAD: {dialog.unread_count})"
                            )
                        if topics_list:
                            forum_str = "\n" + "\n".join(topics_list)

                    overview_lines.append(
                        f"- [{status_str} {chat_type}] {dialog.name} (ID: `{dialog.id}`){part_str}{desc_str}{unread}{forum_str}"
                    )

            # 3. Финальная сборка
            res_str = ""
            if unread_blocks:
                res_str += "ТРЕБУЮТ ВНИМАНИЯ (Непрочитанные личные сообщения):\n"
                res_str += "\n\n".join(unread_blocks)
                res_str += "\n\n---\n\n"

            if overview_lines:
                res_str += "ПОСЛЕДНИЕ ДИАЛОГИ (Общий список):\n"
                res_str += "\n".join(overview_lines)
                if total_dialogs > len(overview_lines):
                    hidden = total_dialogs - len(overview_lines)
                    res_str += f"\n\n...и еще {hidden} чатов скрыто для экономии контекста. Для просмотра - сооветствующая функция."
            else:
                res_str += "Список диалогов пуст."

            self.state.last_chats = res_str

        except Exception as e:
            system_logger.error(f"[Telethon] Ошибка обновления стейта: {e}")

    # ==========================================================
    # ОБРАБОТЧИКИ (HANDLERS)
    # ==========================================================

    async def _on_outgoing_message(self, event: events.NewMessage.Event) -> None:
        """Триггер на исходящие (наши) сообщения: форсируем обновление стейта."""
        await self._update_state(force=True)

    async def _on_private_message(self, event: events.NewMessage.Event) -> None:
        """Перехват ЛС. Динамически подтягивает контекст (историю) чата."""
        await self._update_state(force=True)

        client = self.tg_client.client()
        msg_obj = event.message

        sender_name = await TelethonMessageParser.get_sender_name(msg_obj)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)
        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, None)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        media_tag = TelethonMessageParser.parse_media(msg_obj)
        msg_text = msg_obj.text or ""
        base_text = f"{media_tag} {msg_text}".strip() if media_tag else msg_text

        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        # Динамический расчет истории сообщений
        unread_count = await self._get_unread_count(chat)
        limit = min(50, max(self.config.incoming_history_limit, unread_count))
        history = await self._fetch_recent_history(chat, limit=limit)

        payload = {
            "message": enriched_message,
            "raw_text": msg_text,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
            "msg_id": msg_obj.id,
        }
        if history:
            payload["recent_history"] = history

        await self.bus.publish(Events.TELETHON_MESSAGE_INCOMING, **payload)

    async def _on_group_message(self, event: events.NewMessage.Event) -> None:
        """Перехват сообщений в группах. Резолвит ветки (Topics) на форумах."""
        if event.mentioned:
            event_type = Events.TELETHON_GROUP_MENTION
        else:
            event_type = Events.TELETHON_GROUP_MESSAGE

        await self._update_state(force=True)

        client = self.tg_client.client()
        msg_obj = event.message

        sender_name = await TelethonMessageParser.get_sender_name(msg_obj)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)

        topic_id = None
        topic_name = None
        if getattr(msg_obj, "reply_to", None) and getattr(
            msg_obj.reply_to, "forum_topic", False
        ):
            topic_id = msg_obj.reply_to.reply_to_top_id or msg_obj.reply_to.reply_to_msg_id
            if topic_id:
                try:
                    topic_msg = await client.get_messages(chat, ids=topic_id)
                    if (
                        topic_msg
                        and getattr(topic_msg, "action", None)
                        and hasattr(topic_msg.action, "title")
                    ):
                        topic_name = topic_msg.action.title
                except Exception:
                    pass

        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, topic_id)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        media_tag = TelethonMessageParser.parse_media(msg_obj)
        msg_text = msg_obj.text or ""
        base_text = f"{media_tag} {msg_text}".strip() if media_tag else msg_text

        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        payload = {
            "message": enriched_message,
            "raw_text": msg_text,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
            "msg_id": msg_obj.id,
        }

        if topic_id:
            payload["topic_id"] = topic_id
            if topic_name:
                payload["topic_name"] = topic_name

        if event.mentioned:
            unread_count = await self._get_unread_count(chat)
            limit = min(50, max(self.config.incoming_history_limit, unread_count))
            history = await self._fetch_recent_history(chat, limit=limit)
            if history:
                payload["recent_history"] = history

        await self.bus.publish(event_type, **payload)

    async def _on_reaction(self, event: Any) -> None:
        """Перехватывает реакции (эмодзи) на сообщения."""
        if not isinstance(event, UpdateMessageReactions):
            return

        await self._update_state()

        try:
            chat_id = utils.get_peer_id(event.peer)
        except Exception:
            chat_id = "Unknown"

        reactions_str = "Реакции удалены"
        if getattr(event, "reactions", None) and getattr(event.reactions, "results", None):
            r_list = [
                f"{getattr(r.reaction, 'emoticon', '[CustomEmoji]')} x{r.count}"
                for r in event.reactions.results
            ]
            if r_list:
                reactions_str = ", ".join(r_list)

        await self.bus.publish(
            Events.TELETHON_MESSAGE_REACTION,
            chat_id=chat_id,
            message_id=event.msg_id,
            reactions=reactions_str,
        )

    async def _on_channel_message(self, event: events.NewMessage.Event) -> None:
        """Перехватывает посты в каналах."""
        await self._update_state()

        client = self.tg_client.client()
        msg_obj = event.message

        sender_name = await TelethonMessageParser.get_sender_name(msg_obj)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)
        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, None)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        media_tag = TelethonMessageParser.parse_media(msg_obj)
        msg_text = msg_obj.text or ""
        base_text = f"{media_tag} {msg_text}".strip() if media_tag else msg_text

        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        payload = {
            "message": enriched_message,
            "raw_text": msg_text,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
            "msg_id": msg_obj.id,
        }

        await self.bus.publish(Events.TELETHON_CHANNEL_MESSAGE, **payload)

    async def _on_chat_action(self, event: events.ChatAction.Event) -> None:
        """Перехват системных действий в чате (юзер вступил, закреп, смена фото)."""
        await self._update_state()

        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        action_text = "[Системное действие] Произошло системное событие в чате."

        users = [utils.get_display_name(u) for u in event.users] if event.users else []
        users_str = ", ".join(users) if users else "Кто-то"

        if event.user_joined:
            action_text = f"[Системное действие] {users_str} присоединился к чату."
        elif event.user_added:
            action_text = f"[Системное действие] {users_str} был добавлен в чат."
        elif event.user_left:
            action_text = f"[Системное действие] {users_str} покинул чат."
        elif event.user_kicked:
            action_text = f"[Системное действие] {users_str} был исключен."
        elif event.created:
            action_text = (
                f"[Системное действие] Чат '{event.new_title or chat_name}' был создан."
            )
        elif event.new_title:
            action_text = (
                f"[Системное действие] Название чата изменено на '{event.new_title}'."
            )
        elif event.new_photo or event.photo_deleted:
            action_text = "[Системное действие] В чате обновлено или удалено фото."
        elif event.new_pin:
            action_text = "[Системное действие] В чате закреплено новое сообщение."

        payload = {
            "message": action_text,
            "sender_name": "System",
            "chat_name": chat_name,
            "chat_id": event.chat_id,
        }

        await self.bus.publish(Events.TELETHON_CHAT_ACTION, **payload)

    # ==========================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ (HELPERS)
    # ==========================================================

    async def _fetch_recent_history(self, target_entity: Any, limit: int = 5) -> str:
        """
        Вытаскивает N последних сообщений чата (предысторию) для инъекции в событие.
        """
        if not target_entity:
            return ""

        try:
            client = self.tg_client.client()
            msgs = await client.get_messages(target_entity, limit=limit + 1)

            if len(msgs) <= 1:
                return ""

            lines = []
            for msg in reversed(msgs[1:]):
                formatted = await TelethonMessageParser.build_string(
                    client=client,
                    target_entity=target_entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    truncate_text_flag=True,
                )
                lines.append(formatted)

            return "\n" + "\n\n".join(lines)

        except Exception as e:
            system_logger.error(f"[Telegram Telethon] Не удалось подтянуть предысторию: {e}")
            return ""

    async def _get_unread_count(self, peer: Any) -> int:
        """Определяет количество непрочитанных сообщений в чате."""
        try:
            client = self.tg_client.client()
            peer_dialogs = await client(GetPeerDialogsRequest(peers=[peer]))
            if peer_dialogs and peer_dialogs.dialogs:
                return peer_dialogs.dialogs[0].unread_count
        except Exception as e:
            system_logger.debug(f"[TelethonEvents] Ошибка получения unread_count: {e}")
        return 0

    async def _get_topics(self, client: Any, entity: Any, limit: int = 100) -> list:
        """Получает список топиков форума через Raw API Telethon."""
        try:
            from telethon.tl.functions.channels import GetForumTopicsRequest
        except ImportError:
            system_logger.debug("[TelethonChats] GetForumTopicsRequest недоступен.")
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
            return getattr(result, "topics", [])
        except Exception as e:
            system_logger.error(f"[TelethonChats] Ошибка _get_topics: {e}")
            return []

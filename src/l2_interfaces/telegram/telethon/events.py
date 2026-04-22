import time
from typing import Any

from telethon import events, utils
from telethon.tl.types import UpdateMessageReactions

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.utils._message_parser import TelethonMessageParser


class TelethonEvents:
    def __init__(
        self,
        tg_client: TelethonClient,
        state: TelethonState,
        event_bus: EventBus,
    ):
        self.tg_client = tg_client
        self.state = state
        self.bus = event_bus
        self._last_state_update = 0.0

    async def start(self) -> None:
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

        client.add_event_handler(
            self._on_chat_action,
            events.ChatAction(),
        )

        client.add_event_handler(
            self._on_reaction,
            events.Raw(),
        )

        # Слушаем исходящие сообщения
        client.add_event_handler(
            self._on_outgoing_message,
            events.NewMessage(outgoing=True),
        )

        system_logger.info("[Telegram Telethon] Слушатели событий успешно запущены.")

    async def stop(self) -> None:
        system_logger.info("[Telegram Telethon] Слушатели событий успешно остановлены.")

    async def _update_state(self, force: bool = False):
        now = time.time()

        # Если не форсируем, ждем хотя бы 3 секунды (защита от FloodWait)
        if not force and now - self._last_state_update < 3:
            return

        self._last_state_update = now

        client = self.tg_client.client()
        chats = []

        try:
            async for dialog in client.iter_dialogs(limit=self.state.number_of_last_chats):
                entity = dialog.entity

                is_public = bool(getattr(entity, "username", None))
                status_str = "Public" if is_public else "Private"

                participants = getattr(entity, "participants_count", None)
                part_str = f" | {participants} чел." if participants else ""

                unread = f" [{dialog.unread_count} непр.]" if dialog.unread_count > 0 else ""

                if dialog.is_user:
                    bot_tag = " [Bot]" if getattr(entity, "bot", False) else ""
                    chats.append(f"[User] {dialog.name}{bot_tag} (ID: {dialog.id}){unread}")

                    limit = self.state.private_chat_history_limit
                    if limit > 0:
                        try:
                            recent_msgs = await client.get_messages(entity, limit=limit)
                            if recent_msgs:
                                chats.append(f"    Last {limit} messages:")
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
                                    chats.append(indented)
                        except Exception:
                            chats.append("    [Ошибка загрузки истории]")

                elif dialog.is_group:
                    chats.append(
                        f"[{status_str} Group] {dialog.name} (ID: {dialog.id}){part_str}{unread}"
                    )
                elif dialog.is_channel:
                    chats.append(
                        f"[{status_str} Channel] {dialog.name} (ID: {dialog.id}){part_str}{unread}"
                    )

            self.state.last_chats = "\n".join(chats) if chats else "Список диалогов пуст."
        except Exception as e:
            system_logger.error(f"[Telethon] Ошибка обновления стейта: {e}")

    # ==========================================================
    # ЭВЕНТЫ
    # ==========================================================

    async def _on_outgoing_message(self, event: events.NewMessage.Event):
        """Триггер на исходящие сообщения (агент ответил, либо юзер написал с телефона)."""
        # Форсируем обновление стейта, чтобы агент на следующем шаге ReAct видел свой же ответ
        await self._update_state(force=True)

    async def _on_private_message(self, event: events.NewMessage.Event) -> None:
        try:
            await event.message.mark_read()
        except Exception:
            pass

        await self._update_state(force=True)

        client = self.tg_client.client()

        sender_name = TelethonMessageParser.get_sender_name(event.message)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        msg_obj = event.message
        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)
        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, None)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        media_tag = TelethonMessageParser.parse_media(msg_obj)
        msg_text = msg_obj.text or ""
        base_text = f"{media_tag} {msg_text}".strip() if media_tag else msg_text

        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        history = await self._fetch_recent_history(chat, limit=5)

        payload = {
            "message": enriched_message,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
            "msg_id": msg_obj.id,
        }
        if history:
            payload["recent_history"] = history

        await self.bus.publish(Events.TELETHON_MESSAGE_INCOMING, **payload)

    async def _on_group_message(self, event: events.NewMessage.Event):
        if event.mentioned:
            event_type = Events.TELETHON_GROUP_MENTION
            try:
                await event.message.mark_read()
            except Exception:
                pass
        else:
            event_type = Events.TELETHON_GROUP_MESSAGE

        await self._update_state(force=True)

        client = self.tg_client.client()
        sender_name = TelethonMessageParser.get_sender_name(event.message)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        msg_obj = event.message
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
            history = await self._fetch_recent_history(chat, limit=10)
            if history:
                payload["recent_history"] = history

        await self.bus.publish(event_type, **payload)

    async def _on_reaction(self, event) -> None:
        if not isinstance(event, UpdateMessageReactions):
            return

        await self._update_state()

        try:
            chat_id = utils.get_peer_id(event.peer)
        except Exception:
            chat_id = "Unknown"

        reactions_str = "Реакции удалены"
        if getattr(event, "reactions", None) and getattr(event.reactions, "results", None):
            r_list = []
            for r in event.reactions.results:
                emo = getattr(r.reaction, "emoticon", "[CustomEmoji]")
                r_list.append(f"{emo} x{r.count}")

            if r_list:
                reactions_str = ", ".join(r_list)

        await self.bus.publish(
            Events.TELETHON_MESSAGE_REACTION,
            chat_id=chat_id,
            message_id=event.msg_id,
            reactions=reactions_str,
        )

    async def _on_channel_message(self, event: events.NewMessage.Event):
        await self._update_state()

        client = self.tg_client.client()
        sender_name = TelethonMessageParser.get_sender_name(event.message)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        msg_obj = event.message
        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)
        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, None)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        media_tag = TelethonMessageParser.parse_media(msg_obj)
        msg_text = msg_obj.text or ""
        base_text = f"{media_tag} {msg_text}".strip() if media_tag else msg_text

        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        payload = {
            "message": enriched_message,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
            "msg_id": msg_obj.id,
        }

        await self.bus.publish(Events.TELETHON_CHANNEL_MESSAGE, **payload)

    async def _on_chat_action(self, event: events.ChatAction.Event):
        await self._update_state()

        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        action_text = "[Системное действие] Произошло системное событие в чате."

        users = []
        if event.users:
            users = [utils.get_display_name(u) for u in event.users]
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
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # ==========================================================

    async def _fetch_recent_history(self, target_entity: Any, limit: int = 5) -> str:
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

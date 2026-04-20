from telethon import events, utils
from telethon.tl.types import UpdateMessageReactions

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon._message_parser import TelethonMessageParser


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

    async def start(self) -> None:
        client = self.tg_client.client()
        await self._update_state()

        client.add_event_handler(
            self._on_private_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_private),
        )

        client.add_event_handler(
            self._on_group_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_group),
        )

        client.add_event_handler(
            self._on_reaction,
            events.Raw(),
        )

        system_logger.info("[Telegram Telethon] Слушатели событий успешно запущены.")

    async def stop(self) -> None:
        system_logger.info("[Telegram Telethon] Слушатели событий успешно остановлены.")

    async def _update_state(self):
        client = self.tg_client.client()
        chats = []

        async for dialog in client.iter_dialogs(limit=self.state.number_of_last_chats):
            chat_type = "User" if dialog.is_user else "Group" if dialog.is_group else "Channel"
            unread = (
                f" [Непрочитанных: {dialog.unread_count}]" if dialog.unread_count > 0 else ""
            )
            chats.append(f"{chat_type} | ID: {dialog.id} | Название: {dialog.name}{unread}")

        self.state.last_chats = "\n".join(chats) if chats else "Список диалогов пуст."

    # ==========================================================
    # ЭВЕНТЫ
    # ==========================================================
    async def _on_private_message(self, event: events.NewMessage.Event) -> None:
        try:
            await event.message.mark_read()
        except Exception:
            pass

        await self._update_state()

        client = self.tg_client.client()

        # Получаем имя отправителя через умный парсер (решает проблему "Unknown" в каналах)
        sender_name = TelethonMessageParser.get_sender_name(event.message)

        # Получаем имя чата
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        # Обогащаем сообщение (реплаи, форварды, медиа)
        msg_obj = event.message
        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)
        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, None)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        base_text = msg_obj.text or TelethonMessageParser.parse_media(msg_obj)
        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        # Тянем историю
        history = await self._fetch_recent_history(event.chat_id, limit=5)

        payload = {
            "message": enriched_message,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
        }
        if history:
            payload["recent_history"] = history

        await self.bus.publish(Events.TELETHON_MESSAGE_INCOMING, **payload)

    # Отслеживание сообщений в группах
    async def _on_group_message(self, event: events.NewMessage.Event):
        if event.mentioned:
            event_type = Events.TELETHON_GROUP_MENTION
            try:
                await event.message.mark_read()
            except Exception:
                pass
        else:
            event_type = Events.TELETHON_GROUP_MESSAGE

        await self._update_state()

        client = self.tg_client.client()

        sender_name = TelethonMessageParser.get_sender_name(event.message)

        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        msg_obj = event.message
        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)
        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, None)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        base_text = msg_obj.text or TelethonMessageParser.parse_media(msg_obj)
        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        payload = {
            "message": enriched_message,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
        }

        # В группах подтягиваем историю ТОЛЬКО если нас упомянули (экономим запросы)
        if event.mentioned:
            history = await self._fetch_recent_history(event.chat_id, limit=5)
            if history:
                payload["recent_history"] = history

        await self.bus.publish(event_type, **payload)

    # Отслеживание реакций
    async def _on_reaction(self, event) -> None:
        if not isinstance(event, UpdateMessageReactions):
            return

        await self._update_state()

        # Вытаскиваем ID чата, в котором поставили реакцию
        try:
            chat_id = utils.get_peer_id(event.peer)
        except Exception:
            chat_id = "Unknown"

        # Парсим новые реакции
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

    # ==========================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # ==========================================================

    async def _fetch_recent_history(self, chat_id: int, limit: int = 5) -> str:
        """KISS: Быстро подтягивает последние N сообщений в идеальном форматировании."""
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(chat_id)
            msgs = await client.get_messages(target_entity, limit=limit + 1)

            if len(msgs) <= 1:
                return ""

            lines = []
            # Переворачиваем, чтобы читать сверху вниз
            for msg in reversed(msgs[1:]):
                formatted = await TelethonMessageParser.build_string(
                    client=client,
                    target_entity=target_entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    truncate_text=True,  # Защита от простыней текста в контексте
                )
                lines.append(formatted)

            return "\n" + "\n\n".join(lines)
        except Exception as e:
            system_logger.debug(f"[TelethonEvents] Не удалось подтянуть предысторию: {e}")
            return ""

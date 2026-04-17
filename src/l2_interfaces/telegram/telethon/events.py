from telethon import events, utils
from telethon.tl.types import UpdateMessageReactions

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient


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

    async def _on_private_message(self, event: events.NewMessage.Event):
        # Автоматически помечаем прочитанным на уровне Telegram, чтобы не триггерить агента позже
        try:
            await event.message.mark_read()
        except Exception:
            pass

        await self._update_state()

        sender = await event.get_sender()
        sender_name = utils.get_display_name(sender) if sender else "Unknown"
        sender_name = sender_name or "Unknown"

        await self.bus.publish(
            Events.TELETHON_MESSAGE_INCOMING,
            message=event.text,
            sender_name=sender_name,
            chat_id=event.chat_id,
        )

    async def _on_group_message(self, event: events.NewMessage.Event):
        if event.mentioned:
            event_type = Events.TELETHON_GROUP_MENTION
            # Если нас тегнули, сбрасываем счетчик непрочитанных
            try:
                await event.message.mark_read()
            except Exception:
                pass
        else:
            event_type = Events.TELETHON_GROUP_MESSAGE

        await self._update_state()

        sender = await event.get_sender()
        sender_name = utils.get_display_name(sender) if sender else "Unknown"
        sender_name = sender_name or "Unknown"

        await self.bus.publish(
            event_type,
            message=event.text,
            sender_name=sender_name,
            chat_id=event.chat_id,
        )

    async def _on_reaction(self, event):
        if not isinstance(event, UpdateMessageReactions):
            return

        await self._update_state()

        await self.bus.publish(
            Events.TELETHON_MESSAGE_REACTION,
            message_id=event.msg_id,
        )

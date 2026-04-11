from telethon import events
from telethon.tl.types import UpdateMessageReactions

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient


class TelethonEvents:
    """
    Слушатель событий Telegram.
    Обновляет TelethonState и публикует события в EventBus.
    """

    def __init__(
        self,
        tg_client: TelethonClient,
        state: TelethonState,
        event_bus: EventBus,
    ):
        self.tg_client = tg_client
        self.state = state
        self.bus = event_bus

    async def start(self):
        """Регистрирует обработчики и делает первичную сборку стейта."""

        client = self.tg_client.client()

        # Первичное заполнение стейта
        await self._update_state()

        # Личные сообщения (будят агента)
        client.add_event_handler(
            self._on_private_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_private),
        )

        # Групповые сообщения (фоновые, либо будим при упоминании)
        client.add_event_handler(
            self._on_group_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_group),
        )

        # Реакции (фоновые)
        client.add_event_handler(
            self._on_reaction,
            events.Raw(),  # Обрабатываем сырые апдейты, фильтруем внутри метода
        )

        system_logger.info("[System] TelethonEvents: Слушатели событий успешно запущены.")

    async def _update_state(self):
        """
        Собирает последние N диалогов и обновляет приборную панель (State).
        Вызывается при старте и при каждом новом событии.
        """

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
        """Триггерится при входящем личном сообщении."""

        await self._update_state()

        sender = await event.get_sender()
        sender_name = getattr(sender, "first_name", "Unknown") if sender else "Unknown"

        await self.bus.publish(
            Events.TELETHON_MESSAGE_INCOMING,
            message=event.text,
            sender_name=sender_name,
            chat_id=event.chat_id,
        )

    async def _on_group_message(self, event: events.NewMessage.Event):
        """Триггерится при сообщениях в группах."""

        await self._update_state()

        # Если нас тегнули (@username) или ответили на наше сообщение - это повод проснуться
        if event.mentioned:
            event_type = Events.TELETHON_GROUP_MENTION
        else:
            # Иначе это просто фоновый шум, агент спать не перестанет
            event_type = Events.TELETHON_GROUP_MESSAGE

        sender = await event.get_sender()
        sender_name = getattr(sender, "first_name", "Unknown") if sender else "Unknown"

        await self.bus.publish(
            event_type,
            message=event.text,
            sender_name=sender_name,
            chat_id=event.chat_id,
        )

    async def _on_reaction(self, event):
        """Триггерится при установке/снятии эмодзи-реакций."""

        # Фильтруем только события реакций
        if not isinstance(event, UpdateMessageReactions):
            return

        await self._update_state()

        await self.bus.publish(
            Events.TELETHON_MESSAGE_REACTION,
            message_id=event.msg_id,
        )

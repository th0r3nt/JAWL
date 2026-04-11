import asyncio
from aiogram import Dispatcher, F
from aiogram.types import Message

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.logger import system_logger

from src.l0_state.interfaces.state import AiogramState
from src.l2_interfaces.telegram.aiogram.client import AiogramClient


class AiogramEvents:
    """
    Слушатель событий Aiogram (Bot API).
    Обновляет AiogramState и публикует события в EventBus.
    """

    def __init__(
        self,
        aiogram_client: AiogramClient,
        state: AiogramState,
        event_bus: EventBus,
    ):
        self.client = aiogram_client
        self.state = state
        self.bus = event_bus

        self.dp = Dispatcher()
        self._polling_task: asyncio.Task | None = None

    async def start(self):
        """Регистрирует роутеры и запускает фоновый поллинг."""

        if self._polling_task:
            return

        bot = self.client.bot()

        # Регистрация хендлеров
        self.dp.message.register(self._on_private_message, F.chat.type == "private")
        self.dp.message.register(
            self._on_group_message, F.chat.type.in_({"group", "supergroup"})
        )

        # Сбрасываем старые апдейты, чтобы бот не отвечал на то, что накопилось пока он был выключен
        await bot.delete_webhook(drop_pending_updates=True)

        # Запускаем поллинг как фоновую задачу
        self._polling_task = asyncio.create_task(self.dp.start_polling(bot))
        system_logger.info("[System] AiogramEvents: Фоновый поллинг запущен.")

    async def stop(self):
        """Останавливает поллинг."""

        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

        # Корректно закрываем Dispatcher
        await self.dp.stop_polling()
        system_logger.info("[System] AiogramEvents: Поллинг остановлен.")

    async def _update_state(self, message: Message):
        """
        Сохраняет чат в кэш и формирует строку для приборной панели.
        Работает по принципу MRU (Most Recently Used).
        """

        chat_type = "User" if message.chat.type == "private" else "Group"
        chat_name = message.chat.title or message.chat.full_name or message.from_user.full_name

        # Сохраняем/обновляем чат в словаре (ключи в dict сохраняют порядок добавления с Python 3.7+)
        chat_str = f"{chat_type} | ID: {message.chat.id} | Название: {chat_name}"

        # Удаляем, чтобы при добавлении он оказался в конце (самым свежим)
        self.state._chats_cache.pop(message.chat.id, None)
        self.state._chats_cache[message.chat.id] = chat_str

        # Оставляем только последние N
        if len(self.state._chats_cache) > self.state.number_of_last_chats:
            first_key = next(iter(self.state._chats_cache))
            del self.state._chats_cache[first_key]

        # Переворачиваем, чтобы новые были сверху
        lines = list(self.state._chats_cache.values())[::-1]
        self.state.last_chats = "\n".join(lines)

    async def _on_private_message(self, message: Message):
        """Триггер на сообщения в ЛС бота."""

        await self._update_state(message)

        sender_name = message.from_user.first_name if message.from_user else "Unknown"

        await self.bus.publish(
            Events.AIOGRAM_MESSAGE_INCOMING,
            message=message.text or message.caption or "[Медиа]",
            sender_name=sender_name,
            chat_id=message.chat.id,
        )

    async def _on_group_message(self, message: Message):
        """Триггер на сообщения в группах."""

        await self._update_state(message)

        bot = self.client.bot()
        me = await bot.get_me()

        # Проверяем, тегнули ли бота: через @username или через reply
        is_mentioned = False
        if message.text and me.username in message.text:
            is_mentioned = True
        elif message.reply_to_message and message.reply_to_message.from_user.id == me.id:
            is_mentioned = True

        event_type = (
            Events.AIOGRAM_GROUP_MENTION if is_mentioned else Events.AIOGRAM_GROUP_MESSAGE
        )
        sender_name = message.from_user.first_name if message.from_user else "Unknown"

        await self.bus.publish(
            event_type,
            message=message.text or message.caption or "[Медиа]",
            sender_name=sender_name,
            chat_id=message.chat.id,
        )

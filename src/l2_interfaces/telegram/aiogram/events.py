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

    async def start(self) -> None:
        """Регистрирует роутеры и запускает фоновый поллинг."""

        if self._polling_task:
            return

        bot = self.client.bot()

        # Регистрация хендлеров
        self.dp.message.register(self._on_private_message, F.chat.type == "private")
        self.dp.message.register(
            self._on_group_message, F.chat.type.in_({"group", "supergroup"})
        )

        self.dp.message.register(
            self._on_system_message,
            F.content_type.in_(
                {
                    "new_chat_members",
                    "left_chat_member",
                    "new_chat_title",
                    "new_chat_photo",
                    "delete_chat_photo",
                    "pinned_message",
                }
            ),
        )

        # Сбрасываем старые апдейты, чтобы бот не отвечал на то, что накопилось пока он был выключен
        await bot.delete_webhook(drop_pending_updates=True)

        # Запускаем поллинг как фоновую задачу
        self._polling_task = asyncio.create_task(self.dp.start_polling(bot))
        system_logger.info("[Telegram Aiogram] Фоновый поллинг запущен.")

    async def stop(self) -> None:
        """Останавливает поллинг."""

        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

        # Корректно закрываем Dispatcher
        try:
            await self.dp.stop_polling()
        except RuntimeError:
            pass  # Игнорируем ошибку "Polling is not started", если он не успел запуститься

        system_logger.info("[Telegram Aiogram] Фоновый поллинг остановлен.")

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
            msg_id=message.message_id,
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
            msg_id=message.message_id,
        )

    async def _on_system_message(self, message: Message):
        """Триггер на системные события (вход, выход, смена названия и т.д.)."""

        await self._update_state(message)

        action_text = "[Системное действие]"

        if message.new_chat_members:
            users = ", ".join([u.first_name for u in message.new_chat_members if u.first_name])
            action_text = f"[Системное действие] {users} присоединился к чату."

        elif message.left_chat_member:
            action_text = (
                f"[Системное действие] {message.left_chat_member.first_name} покинул чат."
            )

        elif message.new_chat_title:
            action_text = (
                f"[Системное действие] Название чата изменено на '{message.new_chat_title}'."
            )

        elif message.pinned_message:
            action_text = "[Системное действие] Закреплено новое сообщение."

        elif message.new_chat_photo or message.delete_chat_photo:
            action_text = "[Системное действие] Фото чата было изменено/удалено."

        payload = {
            "message": action_text,
            "sender_name": "System",
            "chat_id": message.chat.id,
        }

        await self.bus.publish(Events.AIOGRAM_CHAT_ACTION, **payload)

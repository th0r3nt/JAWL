"""
Background Aiogram events listener (Dispatcher).

Uses Long Polling to intercept messages and system chat events.
Analyzes incoming data, updates L0 State, and publishes events to EventBus
to wake up the agent core.
"""

import asyncio
from typing import Optional

from aiogram import Dispatcher, F
from aiogram.types import Message

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.logger import main_logger

from src.l2_interfaces.telegram.aiogram.state import AiogramState
from src.l2_interfaces.telegram.aiogram.client import AiogramClient


class AiogramEvents:
    """
    Background Aiogram poller.
    Orchestrates routers, handlers, and EventBus communication.
    """

    def __init__(
        self,
        aiogram_client: AiogramClient,
        state: AiogramState,
        event_bus: EventBus,
    ) -> None:
        """
        Initializes the events listener.

        Args:
            aiogram_client (AiogramClient): Initialized bot client.
            state (AiogramState): L0 state to update active chats list.
            event_bus (EventBus): Global event bus.
        """
        self.client = aiogram_client
        self.state = state
        self.bus = event_bus

        self.dp = Dispatcher()
        self._polling_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """
        Registers message handlers, resets old Webhook/Updates,
        and starts Long Polling as a background task.
        """
        if self._polling_task:
            return

        bot = self.client.bot()

        # Register handlers with chat type filters
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

        # Drop pending updates accumulated during offline
        await bot.delete_webhook(drop_pending_updates=True)

        self._polling_task = asyncio.create_task(self.dp.start_polling(bot))
        main_logger.info("[Telegram Aiogram] Background polling started.")

    async def stop(self) -> None:
        """Stops polling and correctly closes the Dispatcher."""
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

        try:
            await self.dp.stop_polling()
        except RuntimeError:
            pass  # Ignore "Polling is not started" error

        main_logger.info("[Telegram Aiogram] Background polling stopped.")

    async def _update_state(self, message: Message) -> None:
        """
        Saves chat to cache and formats string for the dashboard.
        Works on the MRU (Most Recently Used) principle, evicting older dialogues.

        Args:
            message (Message): Incoming message from Aiogram.
        """
        chat_type = "User" if message.chat.type == "private" else "Group"
        chat_name = message.chat.title or message.chat.full_name or message.from_user.full_name

        chat_str = f"{chat_type} | ID: {message.chat.id} | Name: {chat_name}"

        # Remove the key so that upon insertion it is at the end of the dictionary (freshest)
        self.state._chats_cache.pop(message.chat.id, None)
        self.state._chats_cache[message.chat.id] = chat_str

        # Evict old chats if limit is exceeded
        if len(self.state._chats_cache) > self.state.number_of_last_chats:
            first_key = next(iter(self.state._chats_cache))
            del self.state._chats_cache[first_key]
            self.state.recent_messages.pop(first_key, None)

        # Reverse the list so that new (latest) ones are at the top
        lines = list(self.state._chats_cache.values())[::-1]
        self.state.last_chats = "\n".join(lines)

        # Интегрируем сохранение текста сообщений в кэш
        if message.chat.id not in self.state.recent_messages:
            self.state.recent_messages[message.chat.id] = []

        sender_name = message.from_user.first_name if message.from_user else "Unknown"
        msg_text = message.text or message.caption or "[Media]"
        self.state.recent_messages[message.chat.id].append(f"[{sender_name}]: {msg_text}")

        if len(self.state.recent_messages[message.chat.id]) > self.state.recent_messages_limit:
            self.state.recent_messages[message.chat.id].pop(0)

    async def _on_private_message(self, message: Message) -> None:
        """Trigger on incoming private messages (DMs) to the bot."""
        await self._update_state(message)

        sender_name = message.from_user.first_name if message.from_user else "Unknown"

        await self.bus.publish(
            Events.AIOGRAM_MESSAGE_INCOMING,
            message=message.text or message.caption or "[Media]",
            raw_text=message.text or message.caption or "",
            sender_name=sender_name,
            chat_id=message.chat.id,
            msg_id=message.message_id,
        )

    async def _on_group_message(self, message: Message) -> None:
        """Trigger on messages in groups/supergroups."""
        await self._update_state(message)

        bot = self.client.bot()
        me = await bot.get_me()

        # Check if the bot was mentioned: via @username or via reply
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
            message=message.text or message.caption or "[Media]",
            raw_text=message.text or message.caption or "",
            sender_name=sender_name,
            chat_id=message.chat.id,
            msg_id=message.message_id,
        )

    async def _on_system_message(self, message: Message) -> None:
        """Trigger on system service events (join, leave, title change)."""
        await self._update_state(message)

        action_text = "[System action]"

        if message.new_chat_members:
            users = ", ".join([u.first_name for u in message.new_chat_members if u.first_name])
            action_text = f"[System action] {users} joined the chat."

        elif message.left_chat_member:
            action_text = (
                f"[System action] {message.left_chat_member.first_name} left the chat."
            )

        elif message.new_chat_title:
            action_text = f"[System action] Chat title changed to '{message.new_chat_title}'."

        elif message.pinned_message:
            action_text = "[System action] New message pinned."

        elif message.new_chat_photo or message.delete_chat_photo:
            action_text = "[System action] Chat photo was changed/deleted."

        payload = {
            "message": action_text,
            "sender_name": "System",
            "chat_id": message.chat.id,
        }

        await self.bus.publish(Events.AIOGRAM_CHAT_ACTION, **payload)

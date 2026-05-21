"""
Stateful client for working with Telegram Bot API (via Aiogram v3 library).

Manages the aiohttp session, stores the bot instance, and provides a context provider
(dashboard of recent dialogues) for the system prompt.
"""

from typing import Any, Optional
from aiohttp_socks import ProxyConnector
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import Bot

from src.utils.logger import main_logger

from src.l2_interfaces.telegram.aiogram.state import AiogramState


class AiogramClient:
    """
    Manages basic connection to Telegram via Bot API.
    Guarantees safe opening and closing of HTTP sessions.
    """

    def __init__(
        self, bot_token: str, state: AiogramState, proxy_url: Optional[str] = None
    ) -> None:
        """
        Initializes the bot client.

        Args:
            bot_token (str): Token issued by @BotFather.
            state (AiogramState): L0 state (agent dashboard) to store the MRU cache of chats.

        Raises:
            ValueError: If the bot token is empty.
        """

        self.state = state

        if not bot_token:
            raise ValueError("Aiogram requires bot_token.")

        self.bot_token = bot_token
        self._bot: Optional[Bot] = None

        self.proxy_url = proxy_url

    def bot(self) -> Bot:
        """
        Safe getter to retrieve the bot instance.

        Returns:
            Bot: aiogram.Bot instance.

        Raises:
            RuntimeError: If the client has not been started via `start()`.
        """

        if not self._bot:
            raise RuntimeError("AiogramClient is not started. Bot instance is unavailable.")
        return self._bot

    async def start(self) -> None:
        """
        Initializes the bot and makes a test request (get_me) to validate the token.
        Marks the interface as Online upon success.

        Raises:
            Exception: In case of an invalid token or network error.
        """

        main_logger.info("[Telegram Aiogram] Initializing Aiogram client.")

        try:
            # Configure proxy session for aiohttp
            if self.proxy_url:
                if self.proxy_url.startswith("socks"):
                    connector = ProxyConnector.from_url(self.proxy_url)
                    session = AiohttpSession(connector=connector)
                else:
                    session = AiohttpSession(proxy=self.proxy_url)

                self._bot = Bot(token=self.bot_token, session=session)
            else:
                self._bot = Bot(token=self.bot_token)

            # Make a test request to verify the token
            me = await self._bot.get_me()
            main_logger.info(
                f"[Telegram Aiogram] Aiogram successfully authorized as bot: @{me.username}"
            )
            self.state.is_online = True

        except Exception as e:
            main_logger.error(f"[Telegram Aiogram] Critical error starting Aiogram: {e}")
            raise e

    async def stop(self) -> None:
        """
        Correctly closes the aiohttp session and marks the interface as Offline.
        """

        if self._bot:
            await self._bot.session.close()
            main_logger.info("[Telegram Aiogram] Aiogram client stopped.")
            self.state.is_online = False

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Context provider for ContextRegistry.
        Returns a formatted list of recent active chats and their cached messages.
        """

        desc = "Description: Telegram Bot API. Connects to the registered bot account."

        if not self.state.is_online:
            return f"### AIOGRAM [OFF] \n{desc}\nThe interface is disabled."

        if not self.state._chats_cache:
            return f"### AIOGRAM [ON] \n{desc}\nDialogues list is empty."

        lines = ["Active dialogues list:"]
        for chat_id, chat_str in self.state._chats_cache.items():
            lines.append(f"- {chat_str}")
            if chat_id in self.state.recent_messages and self.state.recent_messages[chat_id]:
                lines.append("  Recent messages:")
                for msg in self.state.recent_messages[chat_id]:
                    lines.append(f"    {msg}")

        chats_info = "\n".join(lines)
        return f"### AIOGRAM [ON] \n{desc}\n\n{chats_info}"

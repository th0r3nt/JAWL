"""
Stateful client for working with Telegram User API (Telethon).

Stores session locally in a SQLite file (Session File).
Provides terminal authorization on the first run (manual entry of phone and code)
and provides a context provider with info about the agent's profile and chats.
"""

from typing import Any, Optional
from python_socks import parse_proxy_url
from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest

from src.utils.logger import main_logger
from src.l2_interfaces.telegram.telethon.state import TelethonState


class TelethonClient:
    """
    Manager for connecting to Telegram servers and managing account sessions.
    """

    def __init__(
        self,
        state: TelethonState,
        api_id: int,
        api_hash: str,
        session_path: str,
        timezone: int,
        proxy_url: Optional[str] = None,
    ) -> None:
        """
        Initializes the client.

        Args:
            state (TelethonState): L0 dashboard.
            api_id (int): Telegram application API ID.
            api_hash (str): Telegram application Hash.
            session_path (str): Path to save the .session file on disk.
            timezone (int): Timezone offset (for log formatting).
        """
        self.state = state

        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.timezone = timezone
        self.proxy_url = proxy_url

        self._client: Optional[TelegramClient] = None

    def client(self) -> TelegramClient:
        """
        Safe access to the Telethon instance.

        Returns:
            TelegramClient: Active Telethon client.

        Raises:
            RuntimeError: If `start()` has not been called yet.
        """
        if not self._client:
            raise RuntimeError("TelethonClient is not started. Instance is unavailable.")
        return self._client

    async def start(self) -> None:
        """
        Starts the client and establishes connection.
        If no session exists on disk, requests phone and code entry directly
        in the server console (Telethon library mechanism).

        Raises:
            Exception: In case of network failures or fatal MTProto errors.
        """
        main_logger.info("[Telegram Telethon] Initializing client.")

        try:
            # Parse proxy if it exists
            proxy = parse_proxy_url(self.proxy_url) if self.proxy_url else None

            self._client = TelegramClient(
                self.session_path, self.api_id, self.api_hash, proxy=proxy
            )

            # Built-in Telethon magic for console authorization
            await self._client.start()

            me = await self._client.get_me()
            name = me.username or me.first_name or "Unknown"

            # Immediately pull full profile data after startup
            await self.update_profile_state()

            main_logger.info(f"[Telegram Telethon] Successful authorization as: @{name}")
            self.state.is_online = True

        except Exception as e:
            main_logger.error(f"[Telegram Telethon] Critical error on startup: {e}")
            raise e

    async def stop(self) -> None:
        """Correctly disconnects from Telegram servers."""
        if self._client and self._client.is_connected():
            await self._client.disconnect()
            main_logger.info("[Telegram Telethon] Client disconnected.")
            self.state.is_online = False

    async def update_profile_state(self) -> None:
        """
        Performs GetFullUserRequest to update the agent's profile data
        in L0 State (name, username, bio, personal channel).
        """
        if not self._client:
            return

        try:
            me = await self._client.get_me()
            name = me.first_name or "Unknown"
            if getattr(me, "last_name", None):
                name += f" {me.last_name}"

            username = f"@{me.username}" if me.username else "No @username"

            # FullUser request is required to get "about" (bio) and personal channel
            full_me = await self._client(GetFullUserRequest(me))
            bio = full_me.full_user.about or "Empty"

            # Search for personal channel
            channel_info = ""
            personal_channel_id = getattr(full_me.full_user, "personal_channel_id", None)

            if personal_channel_id:
                try:
                    from telethon import utils

                    channel = await self._client.get_entity(personal_channel_id)
                    channel_name = utils.get_display_name(channel)
                    channel_username = getattr(channel, "username", None)
                    un_str = f" (@{channel_username})" if channel_username else ""

                    channel_info = f"\nPersonal Channel: {channel_name}{un_str} (ID: {personal_channel_id})"
                except Exception:
                    channel_info = f"\nPersonal Channel: ID {personal_channel_id}"

            self.state.account_info = (
                f"Profile: {name} ({username}) | Bio: {bio}{channel_info}\n---"
            )
        except Exception as e:
            main_logger.error(f"[Telegram Telethon] Error updating profile: {e}")
            self.state.account_info = "Profile: Data load error\n---"

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Context provider for ContextRegistry.
        """

        desc = "Description: Telegram User API. Connects to personal Telegram account."
        if not self.state.is_online:
            return f"### TELETHON [OFF]\n{desc}\nThe interface is disabled."

        return f"### TELETHON [ON] \n{desc}\nAccount info: {self.state.account_info}\nIMPORTANT: It is recommended to reply to users who have UNREAD. \n\n{self.state.last_chats}"

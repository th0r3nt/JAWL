"""
Telethon plugin for Telegram User API.
"""

from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.telegram.telethon.state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.events import TelethonEvents

from src.l2_interfaces.telegram.telethon.skills.account import TelethonAccount
from src.l2_interfaces.telegram.telethon.skills.chats import TelethonChats
from src.l2_interfaces.telegram.telethon.skills.messages import TelethonMessages
from src.l2_interfaces.telegram.telethon.skills.moderation import TelethonModeration
from src.l2_interfaces.telegram.telethon.skills.polls import TelethonPolls
from src.l2_interfaces.telegram.telethon.skills.reactions import TelethonReactions
from src.l2_interfaces.telegram.telethon.skills.admin import TelethonAdmin

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class TelethonPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "TELETHON"

    @property
    def description(self) -> str:
        return "Telegram User API. Connects to the personal Telegram account."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.telegram.telethon.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        api_id = env_vars.get("TELETHON_API_ID")
        api_hash = env_vars.get("TELETHON_API_HASH")

        if not api_id or not api_hash:
            main_logger.error(
                "[Telethon] API_ID or API_HASH not found in .env. Interface disabled."
            )
            self.register_off_provider(container.context_registry)
            return []

        config = container.interfaces_config.telegram.telethon
        state = TelethonState(
            number_of_last_chats=config.recent_chats_limit,
            private_chat_history_limit=config.private_chat_history_limit,
        )
        container.l0_states["telethon"] = state

        session_path = str(
            container.local_data_dir
            / "interfaces"
            / "telegram"
            / "telethon"
            / config.session_name
        )
        clean_api_id = int(api_id) if str(api_id).isdigit() else api_id

        client = TelethonClient(
            state=state,
            api_id=clean_api_id,
            api_hash=api_hash,
            session_path=session_path,
            timezone=container.settings.system.timezone,
            proxy_url=env_vars.get("PROXY_URL"),
        )
        events = TelethonEvents(
            tg_client=client, state=state, event_bus=container.event_bus, config=config
        )

        register_instance(TelethonAccount(client))
        register_instance(TelethonChats(client))
        register_instance(TelethonMessages(client))
        register_instance(TelethonModeration(client))
        register_instance(TelethonPolls(client))
        register_instance(TelethonReactions(client))
        register_instance(TelethonAdmin(client))

        container.context_registry.register_provider(
            name="telethon",
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )
        main_logger.info("[Telethon] Interface loaded.")
        return [client, events]

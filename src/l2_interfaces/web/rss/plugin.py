"""
Плагин интерфейса Web RSS.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.web.rss.state import WebRSSState
from src.l2_interfaces.web.rss.client import WebRSSClient
from src.l2_interfaces.web.rss.events import WebRSSEvents
from src.l2_interfaces.web.rss.skills.rss import WebRSSSkills

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class WebRSSPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "WEB RSS"

    @property
    def description(self) -> str:
        return "RSS/Atom feed parsing and tracking."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.web.rss.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        config = container.interfaces_config.web.rss

        state = WebRSSState(recent_limit=config.recent_limit)
        container.l0_states["web_rss"] = state

        client = WebRSSClient(state=state, config=config)

        events = WebRSSEvents(client=client, state=state, event_bus=container.event_bus)

        register_instance(WebRSSSkills(client))

        container.context_registry.register_provider(
            name=self.name.lower().replace(" ", "_"),
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Web RSS] Интерфейс загружен.")
        return [events]

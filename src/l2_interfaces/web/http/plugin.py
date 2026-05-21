"""
Web HTTP interface plugin.

Provides raw requests and file downloading capabilities.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.web.http.state import WebHTTPState
from src.l2_interfaces.web.http.client import WebHTTPClient
from src.l2_interfaces.web.http.skills.requests import WebHTTPRequests

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class WebHTTPPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "WEB HTTP"

    @property
    def description(self) -> str:
        return "Raw HTTP requests and file downloading."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.web.http.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        config = container.interfaces_config.web.http

        # Initialize L0 State and register in the container
        state = WebHTTPState(history_limit=10)
        container.l0_states["web_http"] = state

        client = WebHTTPClient(state=state, config=config)

        register_instance(WebHTTPRequests(client))

        container.context_registry.register_provider(
            name=self.name.lower().replace(" ", "_"),
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Web HTTP] Interface loaded.")
        return []

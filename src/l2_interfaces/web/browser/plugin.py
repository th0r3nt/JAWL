"""
Плагин интерфейса Web Browser (Playwright).
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.web.browser.state import WebBrowserState
from src.l2_interfaces.web.browser.client import WebBrowserClient
from src.l2_interfaces.web.browser.events import WebBrowserEvents

from src.l2_interfaces.web.browser.skills.navigation import BrowserNavigation
from src.l2_interfaces.web.browser.skills.interaction import BrowserInteraction
from src.l2_interfaces.web.browser.skills.extraction import BrowserExtraction

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class WebBrowserPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "WEB BROWSER"

    @property
    def description(self) -> str:
        return "Browser (Playwright) for interactive webpages."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.web.browser.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        config = container.interfaces_config.web.browser

        state = WebBrowserState()
        container.l0_states["web_browser"] = state

        client = WebBrowserClient(
            state=state,
            config=config,
            data_dir=container.local_data_dir,
            proxy_url=env_vars.get("PROXY_URL"),
        )

        events = WebBrowserEvents(client=client)

        register_instance(BrowserNavigation(client))
        register_instance(BrowserInteraction(client))
        register_instance(BrowserExtraction(client))

        container.context_registry.register_provider(
            name="web_browser",
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Web Browser] Интерфейс загружен..")
        return [client, events]

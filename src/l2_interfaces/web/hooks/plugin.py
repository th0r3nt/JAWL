"""
Плагин интерфейса Web Hooks.
Принимает входящие HTTP-соединения и кидает события в EventBus.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.web.hooks.state import WebHooksState
from src.l2_interfaces.web.hooks.client import WebHooksClient
from src.l2_interfaces.web.hooks.events import WebHooksEvents
from src.l2_interfaces.web.hooks.skills.webhooks import WebHooksSkills

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class WebHooksPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "WEB HOOKS"

    @property
    def description(self) -> str:
        return "HTTP server for receiving incoming webhooks."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.web.hooks.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        secret_token = env_vars.get("WEBHOOK_SECRET")
        if not secret_token:
            main_logger.error(
                "[Web Hooks] WEBHOOK_SECRET не задан в .env. Интерфейс принудительно отключен."
            )
            self.register_off_provider(container.context_registry)
            return []

        config = container.interfaces_config.web.hooks

        state = WebHooksState(history_limit=config.history_limit)
        container.l0_states["web_hooks"] = state

        client = WebHooksClient(state=state, config=config, secret_token=secret_token)

        events = WebHooksEvents(
            client=client,
            state=state,
            event_bus=container.event_bus,
            timezone=container.settings.system.timezone,
        )

        register_instance(WebHooksSkills(client))

        container.context_registry.register_provider(
            name=self.name.lower().replace(" ", "_"),
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Web Hooks] Интерфейс загружен..")
        return [events]

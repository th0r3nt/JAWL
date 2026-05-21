"""
Email interface plugin.
"""

from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.email.state import EmailState
from src.l2_interfaces.email.client import EmailClient
from src.l2_interfaces.email.events import EmailEvents
from src.l2_interfaces.email.skills.mail import EmailSkills
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class EmailPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "EMAIL"

    @property
    def description(self) -> str:
        return "Connecting to the specified mailbox account."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.email.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        account = env_vars.get("EMAIL_ACCOUNT")
        password = env_vars.get("EMAIL_PASSWORD")

        if not account or not password:
            main_logger.error("[Email] EMAIL_ACCOUNT or EMAIL_PASSWORD not found. Disabled.")
            self.register_off_provider(container.context_registry)
            return []

        config = container.interfaces_config.email

        state = EmailState(recent_limit=config.recent_limit)
        container.l0_states["email"] = state

        client = EmailClient(state=state, account=account, password=password)

        events = EmailEvents(
            client=client,
            state=state,
            event_bus=container.event_bus,
            interval_sec=config.polling_interval_sec,
        )

        register_instance(EmailSkills(client))

        container.context_registry.register_provider(
            "email", client.get_context_block, ContextSection.INTERFACES
        )

        main_logger.info("[Email] Interface loaded (Plugin).")
        return [client, events]

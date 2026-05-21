"""
Host Terminal interface plugin.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.host.terminal.state import HostTerminalState
from src.l2_interfaces.host.terminal.client import HostTerminalClient
from src.l2_interfaces.host.terminal.events import HostTerminalEvents
from src.l2_interfaces.host.terminal.skills.messages import HostTerminalMessages

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class HostTerminalPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "HOST TERMINAL"

    @property
    def description(self) -> str:
        return "Direct CLI chat with the system operator/user."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.host.terminal.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        config = container.interfaces_config.host.terminal

        state = HostTerminalState(context_limit=config.context_limit)
        container.l0_states["terminal"] = state

        client = HostTerminalClient(
            state=state,
            config=config,
            data_dir=container.local_data_dir,
            agent_name=container.settings.identity.agent_name,
            timezone=container.settings.system.timezone,
        )

        events = HostTerminalEvents(client=client, event_bus=container.event_bus)

        register_instance(HostTerminalMessages(client))

        container.context_registry.register_provider(
            name="host_terminal",
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Host Terminal] Interface loaded.")
        return [client, events]

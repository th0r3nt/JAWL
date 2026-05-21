"""
Calendar interface plugin.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.calendar.state import CalendarState
from src.l2_interfaces.calendar.client import CalendarClient
from src.l2_interfaces.calendar.events import CalendarEvents
from src.l2_interfaces.calendar.skills.management import CalendarManagement

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class CalendarPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "CALENDAR"

    @property
    def description(self) -> str:
        return "Time management and scheduled alarms/timers."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.calendar.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        config = container.interfaces_config.calendar

        state = CalendarState()
        container.l0_states["calendar"] = state

        client = CalendarClient(
            state=state,
            data_dir=container.local_data_dir,
            timezone=container.settings.system.timezone,
            upcoming_events_limit=config.upcoming_events_limit,
        )

        events = CalendarEvents(
            client=client,
            state=state,
            event_bus=container.event_bus,
            polling_interval=config.polling_interval_sec,
        )

        register_instance(CalendarManagement(client))

        container.context_registry.register_provider(
            name=self.name.lower(),
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Calendar] Interface loaded.")
        return [events]

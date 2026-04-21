from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger

from src.l2_interfaces.calendar.client import CalendarClient
from src.l2_interfaces.calendar.events import CalendarEvents
from src.l2_interfaces.calendar.skills.management import CalendarManagement

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_calendar(system: "System") -> List[Any]:
    """Инициализирует интерфейс Календаря."""

    config = system.interfaces_config.calendar

    # Берем готовый стейт прямо из DI-контейнера
    client = CalendarClient(
        state=system.calendar_state,
        data_dir=system.local_data_dir,
        timezone=system.settings.system.timezone,
    )

    events = CalendarEvents(
        client=client,
        state=system.calendar_state,
        event_bus=system.event_bus,
        polling_interval=config.polling_interval_sec,
    )

    # Регистрация навыков
    register_instance(CalendarManagement(client))

    # Регистрация контекста
    system.context_registry.register_provider(
        name="calendar",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )
    system_logger.info("[Calendar] Интерфейс загружен.")

    return [events]  # Возвращаем events для запуска фонового поллинга в main.py

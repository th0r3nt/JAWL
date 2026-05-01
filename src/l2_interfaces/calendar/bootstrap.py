"""
Инициализатор интерфейса Календаря (Calendar).

Оркестрирует создание клиента для работы с JSON-файлом таймеров,
запуск фонового хронометриста (Watchdog) и регистрацию навыков управления временем.
"""

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
    """
    Инициализирует интерфейс Календаря и интегрирует его в систему.

    Args:
        system (System): Главный DI-контейнер фреймворка.

    Returns:
        List[Any]: Список компонентов с жизненным циклом (events),
                   которые будут запущены в основном цикле.
    """
    config = system.interfaces_config.calendar

    # Берем готовый стейт прямо из DI-контейнера
    client = CalendarClient(
        state=system.calendar_state,
        data_dir=system.local_data_dir,
        timezone=system.settings.system.timezone,
        upcoming_events_limit=config.upcoming_events_limit,
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

    return [events]

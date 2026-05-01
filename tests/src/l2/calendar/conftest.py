import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from src.l0_state.interfaces.calendar_state import CalendarState
from src.utils.event.bus import EventBus
from src.l2_interfaces.calendar.client import CalendarClient
from src.l2_interfaces.calendar.events import CalendarEvents
from src.l2_interfaces.calendar.skills.management import CalendarManagement


@pytest.fixture
def calendar_state():
    return CalendarState()


@pytest.fixture
def calendar_client(tmp_path: Path, calendar_state):
    """Изолированный клиент с временной папкой вместо реальной базы."""
    return CalendarClient(
        state=calendar_state, data_dir=tmp_path, timezone=3, upcoming_events_limit=10
    )


@pytest.fixture
def mock_bus():
    """Мок шины событий."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def calendar_events(calendar_client, calendar_state, mock_bus):
    """Слушатель событий."""
    return CalendarEvents(
        client=calendar_client,
        state=calendar_state,
        event_bus=mock_bus,
        polling_interval=15,
    )


@pytest.fixture
def calendar_skills(calendar_client):
    """Навыки для агента."""
    return CalendarManagement(client=calendar_client)

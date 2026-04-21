import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils.event.bus import EventBus
from src.l0_state.interfaces.state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.events import TelethonEvents


async def async_generator(items):
    """Хелпер для имитации асинхронных генераторов (iter_dialogs)."""
    for item in items:
        yield item


@pytest.fixture
def mock_tg_client():
    """Создает мок клиента Telethon."""
    wrapper = MagicMock(spec=TelethonClient)
    inner_client = AsyncMock()
    inner_client.iter_dialogs = MagicMock()
    wrapper.client.return_value = inner_client
    return wrapper


@pytest.fixture
def mock_bus():
    """Создает мок шины событий."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def state():
    return TelethonState(number_of_last_chats=2)


@pytest.fixture
def telethon_events(mock_tg_client, state, mock_bus):
    """Инициализированный обработчик событий."""
    return TelethonEvents(mock_tg_client, state, mock_bus)

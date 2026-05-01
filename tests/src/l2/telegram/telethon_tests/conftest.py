import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils.event.bus import EventBus
from src.utils.settings import TelethonConfig
from src.l0_state.interfaces.telegram.telethon_state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.events import TelethonEvents


async def async_generator(items):
    for item in items:
        yield item


@pytest.fixture
def mock_tg_client():
    wrapper = MagicMock(spec=TelethonClient)
    inner_client = AsyncMock()
    inner_client.iter_dialogs = MagicMock()
    wrapper.client.return_value = inner_client
    return wrapper


@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def state():
    return TelethonState(number_of_last_chats=2)


@pytest.fixture
def telethon_events(mock_tg_client, state, mock_bus):
    config = TelethonConfig(enabled=True, session_name="test", incoming_history_limit=5)
    return TelethonEvents(mock_tg_client, state, mock_bus, config)

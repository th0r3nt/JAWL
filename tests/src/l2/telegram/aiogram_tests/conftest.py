import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils.event.bus import EventBus
from src.l0_state.interfaces.telegram.aiogram_state import AiogramState
from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l2_interfaces.telegram.aiogram.events import AiogramEvents


@pytest.fixture
def mock_bot():
    """Создает мок Aiogram Bot."""
    bot = AsyncMock()
    bot.id = 123456789
    bot.username = "test_bot"
    me = MagicMock()
    me.id = bot.id
    me.username = bot.username
    bot.get_me.return_value = me
    return bot


@pytest.fixture
def mock_client(mock_bot):
    """Создает мок AiogramClient, который всегда возвращает mock_bot."""
    client = MagicMock(spec=AiogramClient)
    client.bot.return_value = mock_bot
    return client


@pytest.fixture
def state():
    """Стейт на 2 чата (для проверки лимита)."""
    return AiogramState(number_of_last_chats=2)


@pytest.fixture
def mock_bus():
    """Мок шины событий."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def aiogram_events(mock_client, state, mock_bus):
    """Инициализированный обработчик событий."""
    return AiogramEvents(mock_client, state, mock_bus)

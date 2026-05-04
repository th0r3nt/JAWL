import pytest
from unittest.mock import AsyncMock, MagicMock
from src.utils.settings import WebHooksConfig
from src.l2_interfaces.web.hooks.state import WebHooksState
from src.l2_interfaces.web.hooks.client import WebHooksClient
from src.l2_interfaces.web.hooks.events import WebHooksEvents


@pytest.fixture
def hooks_state():
    return WebHooksState(history_limit=5)


@pytest.fixture
def hooks_config():
    return WebHooksConfig(enabled=True, host="127.0.0.1", port=8080, history_limit=5)


@pytest.fixture
def hooks_client(hooks_state, hooks_config):
    return WebHooksClient(state=hooks_state, config=hooks_config, secret_token="secret123")


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def hooks_events(hooks_client, hooks_state, mock_bus):
    return WebHooksEvents(
        client=hooks_client, state=hooks_state, event_bus=mock_bus, timezone=3
    )

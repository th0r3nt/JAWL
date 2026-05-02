import pytest
from unittest.mock import AsyncMock, MagicMock
from src.utils.settings import WebRSSConfig, RSSFeedConfig
from src.l2_interfaces.web.rss.state import WebRSSState
from src.l2_interfaces.web.rss.client import WebRSSClient
from src.l2_interfaces.web.rss.events import WebRSSEvents
from src.utils.event.bus import EventBus


@pytest.fixture
def rss_state():
    return WebRSSState(recent_limit=5)


@pytest.fixture
def rss_config():
    return WebRSSConfig(
        enabled=True,
        polling_interval_sec=10,
        recent_limit=2,
        feeds=[
            RSSFeedConfig(name="Habr", url="http://habr.com/rss"),
            RSSFeedConfig(name="GitHub", url="http://github.com/rss"),
        ],
    )


@pytest.fixture
def rss_client(rss_state, rss_config):
    return WebRSSClient(state=rss_state, config=rss_config)


@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def rss_events(rss_client, rss_state, mock_bus):
    return WebRSSEvents(client=rss_client, state=rss_state, event_bus=mock_bus)

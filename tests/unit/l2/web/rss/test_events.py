import pytest
from unittest.mock import MagicMock, AsyncMock
from src.utils.event.registry import Events
from src.l2_interfaces.web.rss.events import WebRSSEvents


@pytest.mark.asyncio
async def test_rss_events_start_skips_if_empty_feeds(rss_state, mock_bus):
    """Тест: Поллер не должен запускаться, если список фидов пуст."""
    config_empty = MagicMock(feeds=[])
    client_empty = MagicMock(config=config_empty)
    events = WebRSSEvents(client_empty, rss_state, mock_bus)

    await events.start()
    assert events._is_running is False
    assert events._polling_task is None


@pytest.mark.asyncio
async def test_rss_events_poll_first_run_does_not_publish(rss_events, rss_client):
    """Тест: При первом запуске мы только собираем ID, чтобы не спамить агента историей."""
    mock_feed = MagicMock()
    mock_feed.entries = [{"id": "entry_1", "title": "News 1", "link": "http://1"}]
    rss_client.fetch_feed = AsyncMock(return_value=mock_feed)

    await rss_events._poll_feeds(is_first_run=True)

    # Убеждаемся, что в кэш упал айдишник
    assert "entry_1" in rss_events._seen_entries
    # В стейт упала новость
    assert "News 1" in rss_events.state.latest_news
    # Но в шину ничего НЕ публиковалось!
    rss_events.bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_rss_events_poll_new_entry_publishes(rss_events, rss_client):
    """Тест: При последующих запусках новые статьи кидают ивенты."""
    mock_feed = MagicMock()
    mock_feed.entries = [{"id": "entry_2", "title": "New Alert", "link": "http://2"}]
    rss_client.fetch_feed = AsyncMock(return_value=mock_feed)

    # Имитируем второй круг (is_first_run=False)
    await rss_events._poll_feeds(is_first_run=False)

    # Проверяем кэш и стейт
    assert "entry_2" in rss_events._seen_entries
    assert "New Alert" in rss_events.state.latest_news

    # Проверяем, что ивент ушел в шину
    rss_events.bus.publish.assert_called_once()
    args = rss_events.bus.publish.call_args[0]
    kwargs = rss_events.bus.publish.call_args[1]

    assert args[0] == Events.RSS_NEW_ENTRY
    assert kwargs["title"] == "New Alert"

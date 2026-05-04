import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l2_interfaces.web.rss.skills.rss import WebRSSSkills
from src.utils.settings import WebRSSConfig


@pytest.mark.asyncio
async def test_list_rss_feeds_success(rss_client):
    skill = WebRSSSkills(rss_client)
    res = await skill.list_feeds()

    assert res.is_success is True
    assert "Habr" in res.message
    assert "GitHub" in res.message


@pytest.mark.asyncio
async def test_list_rss_feeds_empty(rss_client):
    rss_client.config = WebRSSConfig(feeds=[])
    skill = WebRSSSkills(rss_client)

    res = await skill.list_feeds()
    assert res.is_success is True
    assert "пуст" in res.message


@pytest.mark.asyncio
async def test_read_rss_feed_success(rss_client):
    skill = WebRSSSkills(rss_client)

    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {
            "title": "Agent JAWL updated",
            "link": "https://github.com",
            "published": "Today",
            "summary": "Big update <p>with HTML</p>",
        }
    ]
    rss_client.fetch_feed = AsyncMock(return_value=mock_feed)

    # Теперь передаем URL
    res = await skill.read_feed("http://habr.com/rss", limit=1)

    assert res.is_success is True
    assert "Agent JAWL updated" in res.message
    assert "Today" in res.message


@pytest.mark.asyncio
async def test_read_rss_feed_empty(rss_client):
    """Тест: обработка пустой или битой ленты."""
    skill = WebRSSSkills(rss_client)

    mock_feed = MagicMock()
    mock_feed.bozo = True
    mock_feed.entries = []
    rss_client.fetch_feed = AsyncMock(return_value=mock_feed)

    res = await skill.read_feed("http://bad-url.com")

    assert res.is_success is True
    assert "пуста, недоступна или не содержит записей" in res.message

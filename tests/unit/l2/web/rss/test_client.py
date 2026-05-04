import pytest
from src.l2_interfaces.web.rss.client import WebRSSClient
from src.l2_interfaces.web.rss.state import WebRSSState
from src.utils.settings import WebRSSConfig


def test_rss_client_update_status_empty():
    state = WebRSSState()
    config = WebRSSConfig(feeds=[])
    WebRSSClient(state=state, config=config)

    assert "Нет настроенных RSS-лент" in state.feeds_status


@pytest.mark.asyncio
async def test_rss_client_get_context_block(rss_client):
    rss_client.state.is_online = True
    rss_client.state.latest_news = "- [Habr] Новая статья"

    block = await rss_client.get_context_block()

    assert "WEB RSS [ON]" in block
    assert "Habr (http://habr.com/rss)" in block
    assert "Новая статья" in block

    rss_client.state.is_online = False
    block_off = await rss_client.get_context_block()
    assert "WEB RSS [OFF]" in block_off

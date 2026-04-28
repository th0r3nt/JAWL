import pytest
import time
from unittest.mock import AsyncMock, patch
from src.l2_interfaces.web.browser.events import WebBrowserEvents


@pytest.mark.asyncio
async def test_watchdog_closes_idle_browser(browser_client, mock_playwright):
    """Тест: Watchdog закрывает браузер, если время простоя превышает лимит."""
    events = WebBrowserEvents(browser_client)

    # Имитируем открытый браузер
    _, _, _, page_mock = mock_playwright
    browser_client.page = page_mock

    # Делаем вид, что браузер простаивает уже 100 секунд (при лимите 60 в фикстуре)
    browser_client.last_activity_time = time.time() - 100
    browser_client.close_browser = AsyncMock()

    events._is_running = True

    # Останавливаем цикл после одной итерации
    async def fake_sleep(*args, **kwargs):
        events._is_running = False

    with patch("asyncio.sleep", side_effect=fake_sleep):
        await events._loop()

    # Браузер должен быть закрыт
    browser_client.close_browser.assert_called_once()

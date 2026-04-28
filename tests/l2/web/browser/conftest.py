import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.utils.settings import WebBrowserConfig
from src.l0_state.interfaces.state import WebBrowserState
from src.l2_interfaces.web.browser.client import WebBrowserClient


@pytest.fixture
def browser_state():
    return WebBrowserState()


@pytest.fixture
def browser_config():
    return WebBrowserConfig(enabled=True, headless=True, timeout_sec=10, idle_timeout_sec=60)


@pytest.fixture
def browser_client(browser_state, browser_config, tmp_path: Path):
    """Клиент с временной директорией для профиля (куки)."""
    return WebBrowserClient(state=browser_state, config=browser_config, data_dir=tmp_path)


@pytest.fixture
def mock_playwright():
    """Глубокий мок для Playwright, чтобы не запускать реальный браузер в тестах."""
    page_mock = AsyncMock()

    # === Синхронные методы Playwright ===
    page_mock.is_closed = MagicMock(return_value=False)
    page_mock.set_default_timeout = MagicMock()

    # Свойства
    page_mock.url = "https://mock.com"

    # === Асинхронные методы ===
    page_mock.title = AsyncMock(return_value="Mock Title")
    page_mock.goto = AsyncMock()
    page_mock.wait_for_timeout = AsyncMock()
    page_mock.evaluate = AsyncMock()
    page_mock.wait_for_load_state = AsyncMock()

    # Мок для Локаторов (get_by_role и locator)
    locator_mock = AsyncMock()
    locator_mock.click = AsyncMock()
    locator_mock.fill = AsyncMock()
    locator_mock.hover = AsyncMock()
    locator_mock.first = locator_mock

    # Мок для AOM (Aria Snapshot вместо старого Accessibility)
    locator_mock.aria_snapshot = AsyncMock(return_value='- button "Submit"\n- link "Cancel"')

    page_mock.get_by_role = MagicMock(return_value=locator_mock)
    page_mock.locator = MagicMock(return_value=locator_mock)

    # Мок для клавиатуры (press)
    page_mock.keyboard.press = AsyncMock()

    # Контекст
    context_mock = AsyncMock()
    context_mock.new_page = AsyncMock(return_value=page_mock)
    context_mock.storage_state = AsyncMock()

    # Браузер
    browser_mock = AsyncMock()
    browser_mock.new_context = AsyncMock(return_value=context_mock)
    browser_mock.close = AsyncMock()

    # Playwright
    pw_mock = AsyncMock()
    pw_mock.chromium.launch = AsyncMock(return_value=browser_mock)

    return pw_mock, browser_mock, context_mock, page_mock

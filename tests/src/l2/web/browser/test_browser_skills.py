import pytest
from unittest.mock import AsyncMock, patch
from src.l2_interfaces.web.browser.skills.navigation import BrowserNavigation
from src.l2_interfaces.web.browser.skills.interaction import BrowserInteraction
from src.l2_interfaces.web.browser.skills.extraction import BrowserExtraction


@pytest.fixture
def nav_skills(browser_client):
    return BrowserNavigation(browser_client)


@pytest.fixture
def interact_skills(browser_client):
    return BrowserInteraction(browser_client)


@pytest.fixture
def extract_skills(browser_client):
    return BrowserExtraction(browser_client)


# --- NAVIGATION TESTS ---


@pytest.mark.asyncio
async def test_browser_navigate(nav_skills, mock_playwright):
    _, _, _, page_mock = mock_playwright
    nav_skills.client.page = page_mock
    nav_skills.client.ensure_browser = AsyncMock()

    res = await nav_skills.navigate("github.com")

    assert res.is_success is True
    page_mock.goto.assert_called_once_with("https://github.com", wait_until="networkidle")


@pytest.mark.asyncio
async def test_browser_scroll(nav_skills, mock_playwright):
    _, _, _, page_mock = mock_playwright
    nav_skills.client.page = page_mock
    nav_skills.client.ensure_browser = AsyncMock()
    nav_skills.client.update_state_view = AsyncMock()

    res = await nav_skills.scroll("up")

    assert res.is_success is True
    page_mock.evaluate.assert_called_once_with("window.scrollBy(0, -window.innerHeight)")


# --- INTERACTION TESTS ---


@pytest.mark.asyncio
async def test_browser_press_key(interact_skills, mock_playwright):
    _, _, _, page_mock = mock_playwright
    interact_skills.client.page = page_mock
    interact_skills.client.ensure_browser = AsyncMock()
    interact_skills.client.update_state_view = AsyncMock()

    page_mock.keyboard.press = AsyncMock()

    res = await interact_skills.press_key("Enter")

    assert res.is_success is True
    page_mock.keyboard.press.assert_called_once_with("Enter")


@pytest.mark.asyncio
async def test_browser_hover(interact_skills, mock_playwright):
    _, _, _, page_mock = mock_playwright
    interact_skills.client.page = page_mock
    interact_skills.client.ensure_browser = AsyncMock()
    interact_skills.client.update_state_view = AsyncMock()

    locator_mock = AsyncMock()
    page_mock.get_by_role.return_value.first = locator_mock

    res = await interact_skills.hover("button", "Menu")

    assert res.is_success is True
    locator_mock.hover.assert_called_once()


# --- EXTRACTION TESTS ---


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.browser.skills.extraction.validate_sandbox_path")
async def test_browser_take_screenshot(
    mock_validate, extract_skills, mock_playwright, tmp_path
):
    _, _, _, page_mock = mock_playwright
    extract_skills.client.page = page_mock
    extract_skills.client.ensure_browser = AsyncMock()

    mock_file = tmp_path / "screen.png"
    mock_validate.return_value = mock_file

    # Имитируем, что Playwright реально создал файл-картинку, 
    # чтобы Pillow мог ее открыть и нарисовать сетку
    async def mock_screenshot(*args, **kwargs):
        from PIL import Image
        Image.new("RGB", (200, 200), color="white").save(mock_file)

    page_mock.screenshot = AsyncMock(side_effect=mock_screenshot)

    res = await extract_skills.take_screenshot("screen.png")

    assert res.is_success is True
    assert "[SYSTEM_MARKER_IMAGE_ATTACHED:" in res.message
    page_mock.screenshot.assert_called_once()


@pytest.mark.asyncio
async def test_browser_extract_text(extract_skills, mock_playwright):
    _, _, _, page_mock = mock_playwright
    extract_skills.client.page = page_mock
    extract_skills.client.ensure_browser = AsyncMock()

    page_mock.evaluate = AsyncMock(return_value="Clean extracted text")

    res = await extract_skills.extract_text()

    assert res.is_success is True
    assert "Clean extracted text" in res.message
    page_mock.evaluate.assert_called_once_with("document.body.innerText")

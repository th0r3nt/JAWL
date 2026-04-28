import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.browser.client.async_playwright")
async def test_ensure_browser_normal_start(mock_apw, browser_client, mock_playwright):
    """Тест: Обычный запуск браузера без скачивания бинарников."""
    pw_mock, _, _, _ = mock_playwright
    mock_start = AsyncMock(return_value=pw_mock)
    mock_apw.return_value.start = mock_start

    await browser_client.ensure_browser()

    assert browser_client.browser is not None
    assert browser_client.page is not None
    pw_mock.chromium.launch.assert_called_once()


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.browser.client.asyncio.create_subprocess_exec")
@patch("src.l2_interfaces.web.browser.client.async_playwright")
async def test_ensure_browser_auto_install(
    mock_apw, mock_exec, browser_client, mock_playwright
):
    """Тест: Если бинарников нет, клиент сам вызывает playwright install chromium."""
    pw_mock, browser_mock, _, _ = mock_playwright
    mock_start = AsyncMock(return_value=pw_mock)
    mock_apw.return_value.start = mock_start

    # Имитируем ошибку отсутствия браузера при первом запуске
    pw_mock.chromium.launch.side_effect = [
        Exception("playwright install chromium"),  # Первый вызов падает
        browser_mock,  # Второй вызов проходит
    ]

    # Мокаем подпроцесс установки
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock()
    mock_exec.return_value = mock_proc

    await browser_client.ensure_browser()

    assert mock_exec.call_count == 1
    assert "install" in mock_exec.call_args[0]
    assert browser_client.browser is not None


@pytest.mark.asyncio
async def test_close_browser_cleans_up(browser_client, mock_playwright):
    """Тест: Закрытие браузера освобождает ресурсы и стейт."""
    _, browser_mock, context_mock, page_mock = mock_playwright
    browser_client.browser = browser_mock
    browser_client.context = context_mock
    browser_client.page = page_mock

    await browser_client.close_browser()

    # Проверяем сохранение сессии и закрытие
    context_mock.storage_state.assert_called_once()
    browser_mock.close.assert_called_once()

    assert browser_client.browser is None
    assert browser_client.state.is_open is False
    assert "закрыт" in browser_client.state.viewport

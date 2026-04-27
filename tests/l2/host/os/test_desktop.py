# Файл: tests\l2\host_os\test_desktop.py
import pytest
from unittest.mock import patch, MagicMock
from src.l2_interfaces.host.os.skills.desktop import HostOSDesktop


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.webbrowser.open")
async def test_desktop_open_url(mock_open, os_client):
    """Тест: открытие браузера."""
    desktop = HostOSDesktop(os_client)
    mock_open.return_value = True

    res = await desktop.open_url_in_browser("github.com")

    assert res.is_success is True
    # Убеждаемся, что скилл сам подставил https://
    mock_open.assert_called_once_with("https://github.com")


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.subprocess.run")
async def test_desktop_lock_screen(mock_run, os_client):
    """Тест: блокировка экрана."""
    desktop = HostOSDesktop(os_client)

    # Мокаем sys.platform для предсказуемости теста
    with patch("src.l2_interfaces.host.os.skills.desktop.sys.platform", "darwin"):
        res = await desktop.lock_screen()

    assert res.is_success is True
    mock_run.assert_called_once_with(["pmset", "displaysleepnow"])


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.ImageGrab.grab")
async def test_desktop_take_screenshot(mock_grab, os_client):
    """Тест: создание скриншота в песочнице."""
    desktop = HostOSDesktop(os_client)

    mock_image = MagicMock()
    mock_grab.return_value = mock_image

    res = await desktop.take_screenshot("screen.png")

    assert res.is_success is True
    assert "screen.png" in res.message
    mock_image.save.assert_called_once()

    # Проверяем, что файл действительно сохранился в sandbox/download/
    saved_path = mock_image.save.call_args[0][0]
    assert "download" in str(saved_path)
    assert "screen.png" in str(saved_path)


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.ImageGrab.grab")
async def test_desktop_take_screenshot_headless_fallback(mock_grab, os_client):
    """Тест: обработка ошибки, если монитор не найден (VPS/Server)."""
    desktop = HostOSDesktop(os_client)
    mock_grab.side_effect = OSError("screen grab failed")

    res = await desktop.take_screenshot("screen.png")

    assert res.is_success is False
    assert "графический интерфейс" in res.message.lower() or "headless" in res.message.lower()

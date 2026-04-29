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

    # Проверяем, что файл действительно сохранился в sandbox/_system/download/
    saved_path = mock_image.save.call_args[0][0]
    assert "download" in str(saved_path)
    assert "system" in str(saved_path)
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


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.subprocess.check_output")
async def test_desktop_list_active_windows(mock_check_output, os_client):
    """Тест: получение списка окон."""
    desktop = HostOSDesktop(os_client)

    # Мокаем под Mac OS, чтобы не усложнять тест платформозависимыми либами Windows
    with patch("src.l2_interfaces.host.os.skills.desktop.sys.platform", "darwin"):
        mock_check_output.return_value = "Telegram, Google Chrome, Visual Studio Code"
        res = await desktop.list_active_windows()

    assert res.is_success is True
    assert "Telegram" in res.message
    assert "Google Chrome" in res.message
    mock_check_output.assert_called_once()


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.subprocess.run")
async def test_desktop_focus_window(mock_run, os_client):
    """Тест: переключение фокуса окна."""
    desktop = HostOSDesktop(os_client)

    with patch("src.l2_interfaces.host.os.skills.desktop.sys.platform", "darwin"):
        res = await desktop.focus_window("Telegram")

    assert res.is_success is True
    assert "Фокус переключен" in res.message
    mock_run.assert_called_once()


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.subprocess.run")
async def test_desktop_press_hotkey(mock_run, os_client):
    """Тест: эмуляция нажатия горячих клавиш."""
    desktop = HostOSDesktop(os_client)

    # Тестируем Linux ветку (xdotool), так как она самая прозрачная для тестов
    with patch("src.l2_interfaces.host.os.skills.desktop.sys.platform", "linux"), patch(
        "src.l2_interfaces.host.os.skills.desktop.shutil.which", return_value="xdotool"
    ):

        res = await desktop.press_hotkey("ctrl+c")

    assert res.is_success is True
    assert "успешно нажата" in res.message
    mock_run.assert_called_once_with(["xdotool", "key", "ctrl+c"], check=True)


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.ImageGrab.grab")
async def test_desktop_take_screenshot_with_grid(mock_grab, os_client):
    """Тест: создание скриншота с наложенной координатной сеткой."""
    from PIL import Image

    desktop = HostOSDesktop(os_client)

    # Вместо MagicMock подсовываем реальный пустой Image,
    # чтобы код мог вызвать .size и нарисовать сетку без креша
    test_img = Image.new("RGB", (200, 200), color="white")
    mock_grab.return_value = test_img

    res = await desktop.take_screenshot("grid_screen.png", with_grid=True)

    assert res.is_success is True
    # Проверяем, что файл физически сохранился в песочнице
    saved_file = os_client.download_dir / "grid_screen.png"
    assert saved_file.exists()


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.subprocess.run")
async def test_desktop_click_coordinates(mock_run, os_client):
    """Тест: эмуляция клика мышью по координатам."""
    desktop = HostOSDesktop(os_client)

    # Мокаем под Linux для прозрачной проверки через xdotool
    with patch("src.l2_interfaces.host.os.skills.desktop.sys.platform", "linux"), patch(
        "src.l2_interfaces.host.os.skills.desktop.shutil.which", return_value="xdotool"
    ):

        res = await desktop.click_coordinates(x=500, y=300)

    assert res.is_success is True
    assert "Клик по координатам" in res.message
    mock_run.assert_called_once_with(
        ["xdotool", "mousemove", "500", "300", "click", "1"], check=True
    )


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.desktop.subprocess.run")
async def test_desktop_type_text(mock_run, os_client):
    """Тест: эмуляция ввода текста."""
    desktop = HostOSDesktop(os_client)

    with patch("src.l2_interfaces.host.os.skills.desktop.sys.platform", "linux"), patch(
        "src.l2_interfaces.host.os.skills.desktop.shutil.which", return_value="xdotool"
    ):

        res = await desktop.type_text("Hello Agent")

    assert res.is_success is True
    assert "успешно напечатан" in res.message
    mock_run.assert_called_once_with(["xdotool", "type", "Hello Agent"], check=True)

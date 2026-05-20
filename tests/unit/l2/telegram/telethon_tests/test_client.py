import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.client.TelegramClient")
@patch("src.l2_interfaces.telegram.telethon.client.parse_proxy_url")
async def test_telethon_client_with_proxy(mock_parse_proxy, mock_tg_client_cls):
    """Тест: TelethonClient корректно парсит прокси и отдает его в TelegramClient."""
    from src.l2_interfaces.telegram.telethon.client import TelethonClient
    from src.l2_interfaces.telegram.telethon.state import TelethonState

    mock_parse_proxy.return_value = (3, "127.0.0.1", 9050, True, "user", "pass")

    client = TelethonClient(
        state=TelethonState(),
        api_id=123,
        api_hash="hash",
        session_path="session",
        timezone=3,
        proxy_url="socks5://user:pass@127.0.0.1:9050",
    )

    # Мокаем внутренние вызовы
    mock_instance = MagicMock()
    mock_instance.get_me = AsyncMock(return_value=MagicMock(username="TestBot"))
    mock_instance.start = AsyncMock()  # ФИКС: Явно указываем, что start это корутина
    mock_tg_client_cls.return_value = mock_instance
    client.update_profile_state = AsyncMock()

    await client.start()

    # Проверяем, что парсер был вызван
    mock_parse_proxy.assert_called_once_with("socks5://user:pass@127.0.0.1:9050")

    # Проверяем, что в TelegramClient улетел аргумент proxy
    call_kwargs = mock_tg_client_cls.call_args[1]
    assert "proxy" in call_kwargs
    assert call_kwargs["proxy"] == mock_parse_proxy.return_value


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.client.TelegramClient")
async def test_telethon_client_without_proxy(mock_tg_client_cls):
    """Тест: TelethonClient работает без прокси, если URL не передан."""
    from src.l2_interfaces.telegram.telethon.client import TelethonClient
    from src.l2_interfaces.telegram.telethon.state import TelethonState

    client = TelethonClient(
        state=TelethonState(),
        api_id=123,
        api_hash="hash",
        session_path="session",
        timezone=3,
        proxy_url=None,
    )

    mock_instance = MagicMock()
    mock_instance.get_me = AsyncMock(return_value=MagicMock(username="TestBot"))
    mock_instance.start = AsyncMock()  # ФИКС: Явно указываем, что start это корутина
    mock_tg_client_cls.return_value = mock_instance
    client.update_profile_state = AsyncMock()

    await client.start()

    # Проверяем, что proxy=None
    call_kwargs = mock_tg_client_cls.call_args[1]
    assert call_kwargs.get("proxy") is None

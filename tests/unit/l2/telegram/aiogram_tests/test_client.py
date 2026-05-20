import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.l2_interfaces.telegram.aiogram.state import AiogramState
from src.l2_interfaces.telegram.aiogram.client import AiogramClient


def test_client_missing_token():
    """Тест: клиент не должен инициализироваться без токена."""
    state = AiogramState()
    with pytest.raises(ValueError, match="необходим bot_token"):
        AiogramClient(bot_token="", state=state)


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.aiogram.client.Bot")
async def test_aiogram_client_no_proxy(mock_bot_cls):
    """Тест: Инициализация без прокси."""
    client = AiogramClient(bot_token="123:ABC", state=AiogramState(), proxy_url=None)

    mock_bot_instance = MagicMock()
    mock_bot_instance.get_me = AsyncMock()
    mock_bot_cls.return_value = mock_bot_instance

    await client.start()

    # Проверяем, что Bot создан только с токеном
    mock_bot_cls.assert_called_once_with(token="123:ABC")


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.aiogram.client.AiohttpSession")
@patch("src.l2_interfaces.telegram.aiogram.client.Bot")
async def test_aiogram_client_http_proxy(mock_bot_cls, mock_session_cls):
    """Тест: Инициализация с HTTP прокси."""
    client = AiogramClient(
        bot_token="123:ABC", state=AiogramState(), proxy_url="http://127.0.0.1:8080"
    )

    mock_bot_instance = MagicMock()
    mock_bot_instance.get_me = AsyncMock()
    mock_bot_cls.return_value = mock_bot_instance

    await client.start()

    # Проверяем, что создалась сессия с обычным proxy
    mock_session_cls.assert_called_once_with(proxy="http://127.0.0.1:8080")
    # Проверяем, что бот получил сессию
    assert "session" in mock_bot_cls.call_args[1]


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.aiogram.client.ProxyConnector")
@patch("src.l2_interfaces.telegram.aiogram.client.AiohttpSession")
@patch("src.l2_interfaces.telegram.aiogram.client.Bot")
async def test_aiogram_client_socks_proxy(mock_bot_cls, mock_session_cls, mock_connector_cls):
    """Тест: Инициализация с SOCKS5 прокси (должен использовать ProxyConnector)."""
    client = AiogramClient(
        bot_token="123:ABC", state=AiogramState(), proxy_url="socks5://127.0.0.1:9050"
    )

    mock_bot_instance = MagicMock()
    mock_bot_instance.get_me = AsyncMock()
    mock_bot_cls.return_value = mock_bot_instance

    mock_connector_instance = MagicMock()
    mock_connector_cls.from_url.return_value = mock_connector_instance

    await client.start()

    mock_connector_cls.from_url.assert_called_once_with("socks5://127.0.0.1:9050")
    mock_session_cls.assert_called_once_with(connector=mock_connector_instance)

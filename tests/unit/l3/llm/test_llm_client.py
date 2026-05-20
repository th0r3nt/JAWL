import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator


@pytest.fixture
def mock_rotator():
    rotator = MagicMock(spec=APIKeyRotator)
    rotator.get_next_key = MagicMock(return_value="fake_key_123")
    return rotator


def test_llm_client_url_normalization(mock_rotator):
    """Тест: Клиент должен корректно добавлять http/https к URL."""
    client_local = LLMClient(api_url="127.0.0.1:11434", api_keys_rotator=mock_rotator)
    assert client_local.api_url == "http://127.0.0.1:11434"

    client_remote = LLMClient(api_url="api.openai.com/v1", api_keys_rotator=mock_rotator)
    assert client_remote.api_url == "https://api.openai.com/v1"


@pytest.mark.asyncio
@patch("src.l3_agent.llm.client.AsyncOpenAI")
async def test_llm_client_no_proxy(mock_openai, mock_rotator):
    """Тест: получение сессии без прокси."""
    client = LLMClient(
        api_url="http://localhost:8000", api_keys_rotator=mock_rotator, proxy_url=None
    )
    session = client.get_session()  # noqa: F841

    mock_openai.assert_called_once()
    call_kwargs = mock_openai.call_args[1]
    assert call_kwargs["api_key"] == "fake_key_123"
    assert call_kwargs["http_client"] is None


@pytest.mark.asyncio
@patch("src.l3_agent.llm.client.httpx.AsyncClient")
@patch("src.l3_agent.llm.client.AsyncOpenAI")
async def test_llm_client_with_proxy(mock_openai, mock_httpx, mock_rotator):
    """Тест: если прокси передан, создается httpx.AsyncClient и инжектится в OpenAI."""
    mock_http_instance = MagicMock()
    mock_httpx.return_value = mock_http_instance

    client = LLMClient(
        api_url="", api_keys_rotator=mock_rotator, proxy_url="socks5://127.0.0.1:9050"
    )
    session = client.get_session()  # noqa: F841

    mock_httpx.assert_called_once_with(proxy="socks5://127.0.0.1:9050")

    mock_openai.assert_called_once()
    call_kwargs = mock_openai.call_args[1]
    assert call_kwargs["http_client"] == mock_http_instance


@pytest.mark.asyncio
async def test_llm_client_no_key_raises_error(mock_rotator):
    mock_rotator.get_next_key = MagicMock(return_value=None)
    client = LLMClient(api_url="", api_keys_rotator=mock_rotator)

    with pytest.raises(RuntimeError, match="Нет доступных API ключей"):
        client.get_session()


@pytest.mark.asyncio
async def test_llm_client_close(mock_rotator):
    client = LLMClient(api_url="http://localhost", api_keys_rotator=mock_rotator)
    session = client.get_session()

    with patch.object(session, "close", new_callable=AsyncMock) as mock_close:
        await client.close()
        mock_close.assert_awaited_once()
        assert len(client._sessions) == 0

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

    client_ready = LLMClient(
        api_url="https://api.anthropic.com", api_keys_rotator=mock_rotator
    )
    assert client_ready.api_url == "https://api.anthropic.com"


@pytest.mark.asyncio
async def test_llm_client_get_session(mock_rotator):
    """Тест: получение валидной сессии с ключом от ротатора."""
    client = LLMClient(api_url="localhost:8000", api_keys_rotator=mock_rotator)

    session = client.get_session()

    mock_rotator.get_next_key.assert_called_once()
    assert session.api_key == "fake_key_123"
    assert str(session.base_url) == "http://localhost:8000"


@pytest.mark.asyncio
async def test_llm_client_no_key_raises_error(mock_rotator):
    """Тест: если ротатор не выдал ключ, должна быть ошибка."""
    mock_rotator.get_next_key = MagicMock(return_value=None)
    client = LLMClient(api_url="", api_keys_rotator=mock_rotator)

    with pytest.raises(RuntimeError, match="Нет доступных API ключей"):
        client.get_session()


@pytest.mark.asyncio
async def test_llm_client_close(mock_rotator):
    """Тест: корректное закрытие всех закэшированных сессий OpenAI."""
    client = LLMClient(api_url="http://localhost", api_keys_rotator=mock_rotator)

    # Инициализируем сессию (она попадает в кэш)
    session = client.get_session()
    assert len(client._sessions) == 1

    # Подменяем метод close у реального объекта AsyncOpenAI на мок
    with patch.object(session, "close", new_callable=AsyncMock) as mock_close:
        await client.close()

        mock_close.assert_awaited_once()
        assert len(client._sessions) == 0

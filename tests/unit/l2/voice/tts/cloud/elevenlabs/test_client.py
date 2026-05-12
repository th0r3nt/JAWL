import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

from src.l2_interfaces.voice.tts.cloud.elevenlabs.client import CloudElevenLabsTTSClient


@pytest.mark.asyncio
async def test_elevenlabs_client_start_success(el_client: CloudElevenLabsTTSClient):
    """Тест: Клиент успешно грузит квоты и список голосов при старте."""

    # Мокаем внутренний request, чтобы не делать реальные сетевые вызовы
    async def mock_request(method, endpoint, **kwargs):
        if endpoint == "/user":
            return {"subscription": {"character_count": 50, "character_limit": 10000}}
        if endpoint == "/voices":
            return {
                "voices": [
                    {"voice_id": "v1", "name": "Alice"},
                    {"voice_id": "v2", "name": "Bob"},
                ]
            }
        return {}

    el_client.request = AsyncMock(side_effect=mock_request)

    await el_client.start()

    assert el_client.state.is_online is True
    assert el_client.state.character_count == 50
    assert el_client.state.character_limit == 10000

    # Проверяем кэш голосов
    assert len(el_client.state.available_voices_cache) == 2
    assert "Alice (ID: v1)" in el_client.state.available_voices_cache[0]


@pytest.mark.asyncio
async def test_elevenlabs_client_start_failure(el_client: CloudElevenLabsTTSClient):
    """Тест: Ошибка авторизации корректно гасит интерфейс."""

    el_client.request = AsyncMock(side_effect=Exception("Unauthorized"))

    await el_client.start()

    assert el_client.state.is_online is False


@pytest.mark.asyncio
@patch("src.l2_interfaces.voice.tts.cloud.elevenlabs.client.urllib.request.urlopen")
async def test_elevenlabs_client_request_json(
    mock_urlopen, el_client: CloudElevenLabsTTSClient
):
    """Тест: Низкоуровневый request корректно делает POST и парсит JSON."""

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    res = await el_client.request("POST", "/test", body={"text": "hello"})

    assert res == {"status": "ok"}

    # Проверяем, что заголовки собрались правильно
    req_obj = mock_urlopen.call_args[0][0]
    assert req_obj.get_header("Xi-api-key") == "test_key"
    assert req_obj.get_header("Content-type") == "application/json"


@pytest.mark.asyncio
async def test_elevenlabs_get_context_block(el_client: CloudElevenLabsTTSClient):
    """Тест: Формирование блока контекста."""
    el_client.state.is_online = True
    el_client.state.character_count = 100
    el_client.state.character_limit = 500

    block = await el_client.get_context_block()

    assert "ELEVENLABS TTS [ON]" in block
    assert "100/500" in block

"""
Тесты для Stateful-клиента Cloud Whisper STT.

Проверяют логику инициализации сессий OpenAI SDK и передачу параметров.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.l2_interfaces.voice.stt.cloud.whisper.client import CloudWhisperSTTClient


@pytest.mark.asyncio
@patch("src.l2_interfaces.voice.stt.cloud.whisper.client.AsyncOpenAI")
async def test_whisper_client_start_stop(
    mock_openai: MagicMock, whisper_client: CloudWhisperSTTClient
) -> None:
    """Тест: Клиент успешно создает и закрывает сессию AsyncOpenAI."""
    mock_openai_instance = AsyncMock()
    mock_openai.return_value = mock_openai_instance

    await whisper_client.start()
    assert whisper_client.state.is_online is True
    mock_openai.assert_called_once_with(
        api_key="fake_api_key",
        base_url="http://fake.api.url",
        timeout=60,
    )

    await whisper_client.stop()
    assert whisper_client.state.is_online is False
    mock_openai_instance.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_whisper_client_transcribe(whisper_client: CloudWhisperSTTClient) -> None:
    """Тест: Клиент правильно вызывает метод API и возвращает текст."""
    whisper_client._client = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = "Распознанный текст"
    whisper_client._client.audio.transcriptions.create.return_value = mock_response

    file_tuple = ("test.mp3", b"dummy_audio_bytes")
    text = await whisper_client.transcribe(file_tuple)

    assert text == "Распознанный текст"
    whisper_client._client.audio.transcriptions.create.assert_called_once_with(
        model="whisper-1",
        file=file_tuple,
        temperature=0.2,
    )


@pytest.mark.asyncio
async def test_whisper_client_transcribe_not_started(
    whisper_client: CloudWhisperSTTClient,
) -> None:
    """Тест: Защита от вызова без инициализированного клиента."""
    with pytest.raises(RuntimeError, match="не инициализирован"):
        await whisper_client.transcribe(("file", b""))


@pytest.mark.asyncio
async def test_whisper_client_get_context_block(whisper_client: CloudWhisperSTTClient) -> None:
    """Тест: Корректное формирование блока контекста агента."""
    whisper_client.state.is_online = True
    whisper_client.state.add_history("recording.mp3")

    block = await whisper_client.get_context_block()

    assert "CLOUD WHISPER STT [ON]" in block
    assert "http://fake.api.url" in block
    assert "whisper-1" in block
    assert "recording.mp3" in block

    whisper_client.state.is_online = False
    assert "OFF" in await whisper_client.get_context_block()

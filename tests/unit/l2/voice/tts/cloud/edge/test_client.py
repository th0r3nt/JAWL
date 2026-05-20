import pytest
from unittest.mock import AsyncMock, patch

from src.l2_interfaces.voice.tts.cloud.edge.client import EdgeClient


@pytest.mark.asyncio
@patch("src.l2_interfaces.voice.tts.cloud.edge.client.edge_tts")
async def test_edge_client_start_success(mock_edge_tts, edge_client: EdgeClient):
    """Тест: Клиент успешно грузит список голосов при старте."""

    # Мокаем ответ от библиотеки edge_tts
    mock_edge_tts.list_voices = AsyncMock(
        return_value=[
            {"ShortName": "ru-RU-SvetlanaNeural", "Locale": "ru-RU", "Gender": "Female"},
            {"ShortName": "en-US-GuyNeural", "Locale": "en-US", "Gender": "Male"},
        ]
    )

    await edge_client.start()

    assert edge_client.state.is_online is True
    # Проверяем кэш голосов
    assert len(edge_client.state.available_voices_cache) == 2
    assert "ru-RU-SvetlanaNeural" in edge_client.state.available_voices_cache[0]


@pytest.mark.asyncio
async def test_edge_get_context_block(edge_client: EdgeClient):
    """Тест: Формирование блока контекста."""
    edge_client.state.is_online = True
    edge_client.state.available_voices_cache = ["ru-RU-SvetlanaNeural (ru-RU, Female)"]

    block = await edge_client.get_context_block()

    assert "EDGE TTS [ON]" in block
    assert "Microsoft Edge API" in block
    assert "ru-RU-SvetlanaNeural" in block

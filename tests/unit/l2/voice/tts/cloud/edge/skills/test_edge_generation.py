import pytest
from unittest.mock import AsyncMock

from src.l2_interfaces.voice.tts.cloud.edge.skills.generation import EdgeTTSGeneration


@pytest.fixture
def edge_skills(edge_client, mock_os_client):
    return EdgeTTSGeneration(client=edge_client, host_os=mock_os_client)


@pytest.mark.asyncio
async def test_edge_get_available_voices(edge_skills):
    """Тест: Вывод доступных голосов из кэша."""
    edge_skills.client.state.available_voices_cache = ["Voice1 (ru-RU)", "Voice2 (en-US)"]

    res = await edge_skills.get_available_voices()

    assert res.is_success is True
    assert "Voice1 (ru-RU)" in res.message
    assert "Voice2 (en-US)" in res.message


@pytest.mark.asyncio
async def test_edge_generate_speech_success(edge_skills, mock_os_client):
    """Тест: Успешная генерация и физическое сохранение аудиофайла через гейткипер."""

    # Мокаем физическое создание файла через "API"
    target_path = mock_os_client.sandbox_dir / "test_edge.mp3"

    async def fake_generate(text, voice, output_path):
        with open(output_path, "wb") as f:
            f.write(b"fake_edge_audio")

    edge_skills.client.generate_audio = AsyncMock(side_effect=fake_generate)

    res = await edge_skills.generate_speech(text="Тест", filename="test_edge.mp3")

    assert res.is_success is True
    # assert "сгенерировано" in res.message

    # Проверяем, что файл физически сохранился в песочницу
    assert target_path.exists()
    assert target_path.read_bytes() == b"fake_edge_audio"

    # Проверяем историю стейта
    assert "test_edge.mp3" in edge_skills.client.state.history[0]


@pytest.mark.asyncio
async def test_edge_generate_speech_permission_error(edge_skills):
    """Тест: Попытка сохранить файл вне песочницы блокируется гейткипером."""

    edge_skills.client.generate_audio = AsyncMock()

    # Фикстура mock_os_client настроена бросать PermissionError, если в пути есть 'error'
    res = await edge_skills.generate_speech(
        text="Взломать", filename="../../../error_path.mp3"
    )

    assert res.is_success is False
    assert "SANDBOX: Доступ запрещен" in res.message

    # Убеждаемся, что генерация даже не пыталась запуститься
    edge_skills.client.generate_audio.assert_not_called()


@pytest.mark.asyncio
async def test_edge_generate_speech_empty_text(edge_skills):
    """Тест: Защита от пустых запросов."""
    res = await edge_skills.generate_speech(text="   \n  ")

    assert res.is_success is False
    assert "не может быть пустым" in res.message

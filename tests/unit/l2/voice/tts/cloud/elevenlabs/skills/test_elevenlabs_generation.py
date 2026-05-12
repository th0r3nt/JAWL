import pytest
from unittest.mock import AsyncMock

from src.l2_interfaces.voice.tts.cloud.elevenlabs.skills.generation import (
    CloudElevenLabsTTSGeneration,
)


@pytest.fixture
def gen_skills(el_client, mock_os_client):
    return CloudElevenLabsTTSGeneration(client=el_client, host_os=mock_os_client)


@pytest.mark.asyncio
async def test_get_available_voices(gen_skills):
    """Тест: Вывод доступных голосов из кэша."""
    gen_skills.client.state.available_voices_cache = ["Alice (ID: v1)", "Bob (ID: v2)"]

    res = await gen_skills.get_available_voices()

    assert res.is_success is True
    assert "Alice (ID: v1)" in res.message
    assert "Bob (ID: v2)" in res.message


@pytest.mark.asyncio
async def test_generate_speech_success(gen_skills, mock_os_client):
    """Тест: Успешная генерация и физическое сохранение аудиофайла через гейткипер."""

    # Мокаем запрос к API, пусть вернет фейковые байты
    gen_skills.client.request = AsyncMock(return_value=b"fake_mp3_data")

    # Мокаем фоновое обновление квоты, чтобы не лезло в сеть
    gen_skills.client.update_quota = AsyncMock()

    res = await gen_skills.generate_speech(text="Привет, мир", filename="test.mp3")

    assert res.is_success is True
    assert "сгенерировано" in res.message

    # Проверяем, что файл физически сохранился в песочницу
    saved_file = mock_os_client.sandbox_dir / "test.mp3"
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"fake_mp3_data"

    # Проверяем историю стейта
    assert "test.mp3" in gen_skills.client.state.history[0]


@pytest.mark.asyncio
async def test_generate_speech_permission_error(gen_skills):
    """Тест: Попытка сохранить файл вне песочницы блокируется гейткипером."""

    # Явно мокаем request, чтобы можно было проверить assert_not_called()
    from unittest.mock import AsyncMock

    gen_skills.client.request = AsyncMock()

    # Фикстура mock_os_client настроена бросать PermissionError, если в пути есть 'error'
    res = await gen_skills.generate_speech(text="Взломать", filename="../../../error_path.mp3")

    assert res.is_success is False
    assert "SANDBOX: Доступ запрещен" in res.message

    # Убеждаемся, что сетевой запрос к API даже не пытался отправиться
    gen_skills.client.request.assert_not_called()


@pytest.mark.asyncio
async def test_generate_speech_empty_text(gen_skills):
    """Тест: Защита от пустых запросов, чтобы не тратить API."""
    res = await gen_skills.generate_speech(text="   \n  ")

    assert res.is_success is False
    assert "не может быть пустым" in res.message

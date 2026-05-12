"""
Тесты для навыка транскрибации (Speech-to-Text).

Проверяют логику защиты от переполнения API (размер файла),
Path Traversal (через гейткипер) и неподдерживаемых форматов.
"""

import pytest
import stat
from pathlib import Path
from unittest.mock import AsyncMock

from src.l2_interfaces.voice.stt.cloud.whisper.skills.transcribation import (
    CloudWhisperSTTTranscribation,
)


@pytest.fixture
def whisper_skills(whisper_client, mock_os_client):
    """Сборка навыка с моками клиента и гейткипера."""
    return CloudWhisperSTTTranscribation(client=whisper_client, host_os=mock_os_client)


@pytest.mark.asyncio
async def test_transcribe_audio_success(
    whisper_skills: CloudWhisperSTTTranscribation, mock_os_client, tmp_path: Path
) -> None:
    """Тест: Успешная транскрибация аудиофайла и сохранение лога в стейт."""
    test_file = mock_os_client.sandbox_dir / "voice.mp3"
    test_file.write_bytes(b"fake_audio_data")

    whisper_skills.client.transcribe = AsyncMock(return_value="Привет, ИИ!")

    res = await whisper_skills.transcribe_audio("voice.mp3")

    assert res.is_success is True
    assert "Привет, ИИ!" in res.message
    assert "voice.mp3" in whisper_skills.client.state.recent_history
    whisper_skills.client.transcribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_transcribe_audio_unsupported_extension(
    whisper_skills: CloudWhisperSTTTranscribation, mock_os_client
) -> None:
    """Тест: Навык отклоняет файлы с неподдерживаемыми расширениями."""
    test_file = mock_os_client.sandbox_dir / "document.txt"
    test_file.write_text("Hello", encoding="utf-8")

    res = await whisper_skills.transcribe_audio("document.txt")

    assert res.is_success is False
    assert "не поддерживается" in res.message


@pytest.mark.asyncio
async def test_transcribe_audio_empty_file(
    whisper_skills: CloudWhisperSTTTranscribation, mock_os_client
) -> None:
    """Тест: Навык отклоняет пустые файлы до вызова API."""
    test_file = mock_os_client.sandbox_dir / "empty.mp3"
    test_file.write_bytes(b"")  # 0 байт

    res = await whisper_skills.transcribe_audio("empty.mp3")

    assert res.is_success is False
    assert "Файл пуст" in res.message


@pytest.mark.asyncio
async def test_transcribe_audio_permission_error(
    whisper_skills: CloudWhisperSTTTranscribation,
) -> None:
    """Тест: Попытка выйти за пределы песочницы (Path Traversal) блокируется гейткипером."""
    # Фикстура настроена так, что строка 'error' триггерит отказ в доступе
    res = await whisper_skills.transcribe_audio("../../../error_secrets.mp3")

    assert res.is_success is False
    assert "SANDBOX: Доступ запрещен" in res.message


@pytest.mark.asyncio
async def test_transcribe_audio_size_limit(
    whisper_skills, mock_os_client, monkeypatch
) -> None:
    """Тест: Файлы больше 25 MB отклоняются, чтобы не вызвать ошибку API."""
    test_file = mock_os_client.sandbox_dir / "huge.mp3"
    test_file.write_bytes(b"data")

    # Подменяем функцию stat, чтобы она возвращала фейковый гигантский размер и корректный флаг файла
    def mock_stat(self_obj, *args, **kwargs):
        class Stat:
            st_size = 26 * 1024 * 1024  # 26 MB
            st_mode = stat.S_IFREG | 0o644  # Имитируем обычный файл, чтобы is_file() не падал

        return Stat()

    monkeypatch.setattr(Path, "stat", mock_stat)

    res = await whisper_skills.transcribe_audio("huge.mp3")

    assert res.is_success is False
    assert "превышает лимит API" in res.message
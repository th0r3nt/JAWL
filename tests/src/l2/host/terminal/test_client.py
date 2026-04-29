import pytest
import json
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_terminal_record_message_and_history(terminal_client):
    """Тест: Сообщения корректно сохраняются в стейт и записываются в JSON."""

    # Эмулируем входящее сообщение
    terminal_client._record_message("User", "Привет, агент", "2026-04-29 12:00")

    # Проверяем L0 State
    assert len(terminal_client.state.recent_messages) == 1
    assert "Привет, агент" in terminal_client.state.recent_messages[0]

    # Проверяем физический файл на диске
    assert terminal_client.history_file.exists()
    with open(terminal_client.history_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 1
    assert data[0]["text"] == "Привет, агент"
    assert data[0]["sender"] == "User"


@pytest.mark.asyncio
async def test_terminal_broadcast_message(terminal_client):
    """Тест: Рассылка сообщений от агента всем подключенным CLI клиентам."""

    # Мокаем активное TCP подключение
    mock_writer = MagicMock()
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()

    terminal_client.active_writers.add(mock_writer)

    # Агент отправляет сообщение
    await terminal_client.broadcast_message("Я проснулся")

    # Проверяем, что сообщение попало в стейт под именем агента
    assert "Я проснулся" in terminal_client.state.recent_messages[0]
    assert "TestAgent" in terminal_client.state.recent_messages[0]

    # Проверяем, что в сокет улетели данные (JSON строка)
    mock_writer.write.assert_called_once()
    written_data = mock_writer.write.call_args[0][0].decode("utf-8")
    assert "Я проснулся" in written_data
    assert "text" in written_data

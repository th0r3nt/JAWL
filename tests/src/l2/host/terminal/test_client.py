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


@pytest.mark.asyncio
async def test_terminal_handle_client_json_payload(terminal_client):
    """
    Тест: TCP-сервер корректно парсит многострочные сообщения, отправленные в формате JSON,
    предотвращая двойное срабатывание событий (дубликатов) в очереди.
    """
    # Мокаем очередь, чтобы отследить, что туда попадет
    terminal_client.incoming_queue = AsyncMock()

    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()

    # Имитируем поток данных из сокета:
    # 1. Успешный Handshake
    # 2. JSON-пакет с текстом, содержащим перенос строки
    # 3. Пустая строка (клиент отключился)
    payload = json.dumps({"text": "Строка 1\nСтрока 2"}) + "\n"

    mock_reader.readline.side_effect = [b"JAWL_HANDSHAKE\n", payload.encode("utf-8"), b""]

    await terminal_client._handle_client(mock_reader, mock_writer)

    # Проверяем, что в очередь сообщений (для EventBus) попал строго ОДИН ивент _MESSAGE
    # Несмотря на то, что внутри текста есть \n
    message_calls = [
        call
        for call in terminal_client.incoming_queue.put.call_args_list
        if call[0][0][0] == "_MESSAGE"
    ]

    assert len(message_calls) == 1
    assert "Строка 1\nСтрока 2" in message_calls[0][0][0][1]

    # Убеждаемся, что в стейт (MRU-кэш) тоже попала только одна запись
    assert len(terminal_client.state.recent_messages) == 1
    assert "Строка 1\nСтрока 2" in terminal_client.state.recent_messages[0]

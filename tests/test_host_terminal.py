import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.utils.settings import HostTerminalConfig
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.state import HostTerminalState
from src.l2_interfaces.host.terminal.client import HostTerminalClient
from src.l2_interfaces.host.terminal.events import HostTerminalEvents
from src.l2_interfaces.host.terminal.skills.messages import HostTerminalMessages


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def config():
    return HostTerminalConfig(enabled=True)


@pytest.fixture
def state():
    return HostTerminalState(number_of_last_messages=2)


@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_reader():
    reader = AsyncMock()
    # Имитируем ввод двух строк и закрытие соединения (пустая строка)
    reader.readline.side_effect = [b"Hello, Agent!\n", b"Wake up\n", b""]
    return reader


@pytest.fixture
def mock_writer():
    writer = MagicMock()
    writer.get_extra_info.return_value = "127.0.0.1:9999"
    writer.drain = AsyncMock()
    return writer


@pytest.fixture
def terminal_client(config, state):
    return HostTerminalClient(config=config, state=state)


# ===================================================================
# TESTS: CLIENT
# ===================================================================


@pytest.mark.asyncio
async def test_client_handle_connection(terminal_client, mock_reader, mock_writer):
    """Тест: клиент читает из TCP-сокета и кладет строки в очередь."""

    await terminal_client._handle_connection(mock_reader, mock_writer)

    # В очереди должно быть 2 сообщения
    assert terminal_client.incoming_messages.qsize() == 2

    msg1 = await terminal_client.incoming_messages.get()
    msg2 = await terminal_client.incoming_messages.get()

    assert msg1 == "Hello, Agent!"
    assert msg2 == "Wake up"

    # После завершения чтения writer должен обнулиться
    assert terminal_client._writer is None


@pytest.mark.asyncio
async def test_client_send_message_success(terminal_client, mock_writer):
    """Тест: успешная запись в сокет, если окно подключено."""
    terminal_client._writer = mock_writer

    result = await terminal_client.send_message("Testing output")

    assert result is True
    mock_writer.write.assert_called_once_with(b"Testing output\n")
    mock_writer.drain.assert_awaited_once()


@pytest.mark.asyncio
async def test_client_send_message_fail(terminal_client):
    """Тест: попытка записи без подключенного окна возвращает False."""
    terminal_client._writer = None  # Окно не подключено

    result = await terminal_client.send_message("Ghost message")

    assert result is False


# ===================================================================
# TESTS: EVENTS
# ===================================================================


@pytest.mark.asyncio
async def test_events_update_state(terminal_client, state, mock_bus):
    """Тест: запись сообщений в стейт соблюдает лимит."""
    events = HostTerminalEvents(terminal_client, state, mock_bus)

    events._update_state("Message 1")
    events._update_state("Message 2")
    events._update_state("Message 3")

    # Лимит state.number_of_last_messages = 2
    lines = state.messages.split("\n")
    assert len(lines) == 2
    assert "Admin: Message 2" in lines[0]
    assert "Admin: Message 3" in lines[1]
    assert "Message 1" not in state.messages


@pytest.mark.asyncio
async def test_events_loop_publishes_event(terminal_client, state, mock_bus):
    """Тест: получение сообщения из очереди генерирует ивент."""
    events = HostTerminalEvents(terminal_client, state, mock_bus)

    # Кладем сообщение в очередь
    await terminal_client.incoming_messages.put("Ping")

    # Запускаем таску вручную, ждем перехвата и тут же отменяем
    task = asyncio.create_task(events._loop())
    events._is_running = True

    await asyncio.sleep(0.01)  # Даем циклу прокрутиться

    events._is_running = False
    task.cancel()

    # Проверяем, что событие ушло в шину
    mock_bus.publish.assert_called_once_with(
        Events.HOST_TERMINAL_MESSAGE_INCOMING,
        message="Ping",
        sender_name="Admin",
    )


# ===================================================================
# TESTS: SKILLS
# ===================================================================


@pytest.mark.asyncio
async def test_skill_send_to_terminal_success(terminal_client, state):
    """Тест навыка: успешная отправка обновляет стейт."""
    skills = HostTerminalMessages(terminal_client, state, agent_name="Agent")

    # Мокаем успешную отправку
    terminal_client.send_message = AsyncMock(return_value=True)

    res = await skills.send_to_terminal("I am alive")

    assert res.is_success is True
    assert "Agent: I am alive" in state.messages
    terminal_client.send_message.assert_called_once_with("I am alive")


@pytest.mark.asyncio
async def test_skill_send_to_terminal_fail(terminal_client, state):
    """Тест навыка: провал отправки не засоряет стейт."""
    skills = HostTerminalMessages(terminal_client, state, "Agent")

    # Мокаем неудачную отправку (окно закрыто)
    terminal_client.send_message = AsyncMock(return_value=False)

    res = await skills.send_to_terminal("Nobody hears me")

    assert res.is_success is False
    assert "не подключено" in res.message
    # Стейт не должен измениться
    assert "Agent: Nobody hears me" not in state.messages

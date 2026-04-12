import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telethon.tl.types import UpdateMessageReactions

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.l0_state.interfaces.state import TelethonState

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.events import TelethonEvents
from src.l2_interfaces.telegram.telethon.skills.messages import TelethonMessages


# ===================================================================
# HELPERS & MOCKS
# ===================================================================


async def async_generator(items):
    """Хелпер для создания асинхронных генераторов (имитация iter_dialogs)."""
    for item in items:
        yield item


@pytest.fixture
def mock_tg_client():
    """Создает мок клиента Telethon."""
    wrapper = MagicMock(spec=TelethonClient)
    inner_client = AsyncMock()

    # iter_dialogs в Telethon возвращает асинхронный генератор мгновенно (без await)
    # Поэтому мы переопределяем этот метод обычным MagicMock, чтобы он не создавал корутину
    inner_client.iter_dialogs = MagicMock()

    wrapper.client.return_value = inner_client
    return wrapper


@pytest.fixture
def mock_bus():
    """Создает мок шины событий."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def state():
    """Стейт на 2 чата."""
    return TelethonState(number_of_last_chats=2)


@pytest.fixture
def telethon_events(mock_tg_client, state, mock_bus):
    """Инициализированный обработчик событий."""
    return TelethonEvents(mock_tg_client, state, mock_bus)


# ===================================================================
# TESTS: EVENTS & STATE
# ===================================================================


@pytest.mark.asyncio
async def test_update_state(telethon_events, mock_tg_client, state):
    """Тест: парсинг диалогов и правильное форматирование в TelethonState."""

    # Имитируем два диалога
    dlg1 = MagicMock()
    dlg1.is_user = True
    dlg1.is_group = False
    dlg1.id = 111
    dlg1.name = "Иван"
    dlg1.unread_count = 1

    dlg2 = MagicMock()
    dlg2.is_user = False
    dlg2.is_group = True
    dlg2.id = 222
    dlg2.name = "Dev Chat"
    dlg2.unread_count = 0

    mock_tg_client.client().iter_dialogs.return_value = async_generator([dlg1, dlg2])

    await telethon_events._update_state()

    # Проверяем, что стейт правильно отформатирован
    assert "User | ID: 111 | Название: Иван [Непрочитанных: 1]" in state.last_chats
    assert "Group | ID: 222 | Название: Dev Chat" in state.last_chats


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.events.utils.get_display_name")
async def test_on_private_message(mock_get_display_name, telethon_events, mock_bus):
    """Тест: личное сообщение публикует правильный ивент."""

    # Заставляем утилиту Telethon всегда возвращать "Alex" в рамках этого теста
    mock_get_display_name.return_value = "Alex"

    # Имитируем входящий ивент (сообщение)
    event = MagicMock()
    event.text = "Привет, агент!"
    event.chat_id = 12345

    sender = MagicMock()
    event.get_sender = AsyncMock(return_value=sender)

    # Пустая история диалогов, чтобы _update_state не упал
    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_private_message(event)

    # Проверяем публикацию в шину
    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_MESSAGE_INCOMING,
        message="Привет, агент!",
        sender_name="Alex",
        chat_id=12345,
    )


@pytest.mark.asyncio
async def test_on_group_message_mentioned(telethon_events, mock_bus):
    """Тест: сообщение в группе с упоминанием публикует MENTION ивент."""
    event = MagicMock()
    event.text = "@agent, как дела?"
    event.chat_id = -100999
    event.mentioned = True  # НАС ТЕГНУЛИ
    event.get_sender = AsyncMock(return_value=None)  # Без имени

    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_group_message(event)

    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_GROUP_MENTION,
        message="@agent, как дела?",
        sender_name="Unknown",
        chat_id=-100999,
    )


@pytest.mark.asyncio
async def test_on_group_message_ignored(telethon_events, mock_bus):
    """Тест: обычное сообщение в группе публикует фоновый ивент (шум)."""
    event = MagicMock()
    event.text = "Просто текст"
    event.chat_id = -100999
    event.mentioned = False  # НАС НЕ ТЕГАЛИ
    event.get_sender = AsyncMock(return_value=None)

    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_group_message(event)

    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_GROUP_MESSAGE,
        message="Просто текст",
        sender_name="Unknown",
        chat_id=-100999,
    )


@pytest.mark.asyncio
async def test_on_reaction(telethon_events, mock_bus):
    """Тест: реакции обрабатываются корректно."""
    # Имитируем сырой объект реакции
    event = UpdateMessageReactions(peer=MagicMock(), msg_id=42, reactions=MagicMock())

    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_reaction(event)

    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_MESSAGE_REACTION,
        message_id=42,
    )


# ===================================================================
# TESTS: SKILLS (Пример)
# ===================================================================


@pytest.mark.asyncio
async def test_send_message_skill(mock_tg_client):
    """Тест навыка агента: отправка сообщения."""
    skills = TelethonMessages(mock_tg_client)

    # Имитируем возвращаемый объект отправленного сообщения
    sent_msg = MagicMock()
    sent_msg.id = 999
    mock_tg_client.client().send_message = AsyncMock(return_value=sent_msg)

    res = await skills.send_message(to_id=123, text="Test")

    assert res.is_success is True
    assert "999" in res.message

    mock_tg_client.client().send_message.assert_called_once_with(
        entity=123, message="Test", silent=False
    )

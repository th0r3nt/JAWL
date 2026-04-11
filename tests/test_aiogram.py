import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.l0_state.interfaces.state import AiogramState

from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l2_interfaces.telegram.aiogram.events import AiogramEvents
from src.l2_interfaces.telegram.aiogram.skills.chats import AiogramChats
from src.l2_interfaces.telegram.aiogram.skills.messages import AiogramMessages
from src.l2_interfaces.telegram.aiogram.skills.moderation import AiogramModeration


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def mock_bot():
    """Создает мок Aiogram Bot."""
    bot = AsyncMock()
    # Задаем фейковые данные бота
    bot.id = 123456789
    bot.username = "test_bot"
    me = MagicMock()
    me.id = bot.id
    me.username = bot.username
    bot.get_me.return_value = me
    return bot


@pytest.fixture
def mock_client(mock_bot):
    """Создает мок AiogramClient, который всегда возвращает mock_bot."""
    client = MagicMock(spec=AiogramClient)
    client.bot.return_value = mock_bot
    return client


@pytest.fixture
def state():
    """Стейт на 2 чата (для проверки лимита)."""
    return AiogramState(number_of_last_chats=2)


@pytest.fixture
def mock_bus():
    """Мок шины событий."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def aiogram_events(mock_client, state, mock_bus):
    """Инициализированный обработчик событий."""
    return AiogramEvents(mock_client, state, mock_bus)


def create_mock_message(chat_id, chat_type, text, from_user_name="John"):
    """Хелпер для создания мок-сообщения Aiogram."""
    msg = MagicMock()
    msg.chat.id = chat_id
    msg.chat.type = chat_type
    msg.chat.title = f"Title_{chat_id}"
    msg.chat.full_name = f"Name_{chat_id}"

    msg.from_user = MagicMock()
    msg.from_user.first_name = from_user_name
    msg.from_user.id = 999

    msg.text = text
    msg.caption = None
    msg.reply_to_message = None
    return msg


# ===================================================================
# TESTS: CLIENT
# ===================================================================


def test_client_missing_token():
    """Тест: клиент не должен инициализироваться без токена."""
    with pytest.raises(ValueError, match="необходим bot_token"):
        AiogramClient(bot_token="")


# ===================================================================
# TESTS: EVENTS & STATE
# ===================================================================


@pytest.mark.asyncio
async def test_update_state_mru_logic(aiogram_events, state):
    """Тест: кэш чатов должен соблюдать лимит (2) и логику Most Recently Used."""

    msg1 = create_mock_message(111, "private", "1")
    msg2 = create_mock_message(222, "group", "2")
    msg3 = create_mock_message(333, "private", "3")

    # Шлем 3 сообщения
    await aiogram_events._update_state(msg1)
    await aiogram_events._update_state(msg2)
    await aiogram_events._update_state(msg3)

    # В кэше должно остаться ровно 2 чата (222 и 333), так как 111 был вытеснен
    assert len(state._chats_cache) == 2
    assert 111 not in state._chats_cache
    assert 333 in state._chats_cache

    # Проверяем, что в форматированной строке стейта последний чат (333) идет самым первым сверху
    assert "ID: 333" in state.last_chats.split("\n")[0]


@pytest.mark.asyncio
async def test_on_private_message(aiogram_events, mock_bus):
    """Тест: личное сообщение генерирует правильный ивент."""
    msg = create_mock_message(100, "private", "Привет", "Alex")

    await aiogram_events._on_private_message(msg)

    mock_bus.publish.assert_called_once_with(
        Events.AIOGRAM_MESSAGE_INCOMING,
        message="Привет",
        sender_name="Alex",
        chat_id=100,
    )


@pytest.mark.asyncio
async def test_on_group_message_mention(aiogram_events, mock_bus):
    """Тест: сообщение в группе с упоминанием бота (@test_bot) генерирует MENTION."""
    msg = create_mock_message(200, "group", "Эй @test_bot, ответь", "Bob")

    await aiogram_events._on_group_message(msg)

    mock_bus.publish.assert_called_once_with(
        Events.AIOGRAM_GROUP_MENTION,
        message="Эй @test_bot, ответь",
        sender_name="Bob",
        chat_id=200,
    )


@pytest.mark.asyncio
async def test_on_group_message_background(aiogram_events, mock_bus):
    """Тест: обычное сообщение в группе генерирует фоновый ивент."""
    msg = create_mock_message(200, "group", "Обычный текст", "Bob")

    await aiogram_events._on_group_message(msg)

    mock_bus.publish.assert_called_once_with(
        Events.AIOGRAM_GROUP_MESSAGE,
        message="Обычный текст",
        sender_name="Bob",
        chat_id=200,
    )


# ===================================================================
# TESTS: SKILLS
# ===================================================================


@pytest.mark.asyncio
async def test_chats_get_chats(state, mock_client):
    """Тест: get_chats возвращает данные из кэша стейта."""
    skills = AiogramChats(mock_client, state)

    # Кэш пуст
    res_empty = await skills.get_chats()
    assert "Список чатов пуст" in res_empty.message

    # Имитируем заполненный кэш
    state._chats_cache[1] = "Chat 1"
    state._chats_cache[2] = "Chat 2"

    res = await skills.get_chats()
    assert res.is_success is True
    # Переворот списка должен вернуть Chat 2 первым
    assert "Chat 2\nChat 1" in res.message


@pytest.mark.asyncio
async def test_messages_send(mock_client, mock_bot):
    """Тест: успешная отправка сообщения."""
    skills = AiogramMessages(mock_client)

    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 777
    mock_bot.send_message.return_value = mock_sent_msg

    res = await skills.send_message(chat_id=123, text="Test")

    assert res.is_success is True
    assert "777" in res.message
    mock_bot.send_message.assert_called_once_with(
        chat_id=123, text="Test", reply_to_message_id=None
    )


@pytest.mark.asyncio
async def test_moderation_ban(mock_client, mock_bot):
    """Тест: бан пользователя в группе."""
    skills = AiogramModeration(mock_client)

    res = await skills.ban_user(chat_id=-100500, user_id=42)

    assert res.is_success is True
    mock_bot.ban_chat_member.assert_called_once_with(chat_id=-100500, user_id=42)

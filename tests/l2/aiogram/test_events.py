import pytest
from unittest.mock import MagicMock
from src.utils.event.registry import Events


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


@pytest.mark.asyncio
async def test_update_state_mru_logic(aiogram_events, state):
    """Тест: кэш чатов должен соблюдать лимит (2) и логику Most Recently Used."""
    msg1 = create_mock_message(111, "private", "1")
    msg2 = create_mock_message(222, "group", "2")
    msg3 = create_mock_message(333, "private", "3")

    await aiogram_events._update_state(msg1)
    await aiogram_events._update_state(msg2)
    await aiogram_events._update_state(msg3)

    assert len(state._chats_cache) == 2
    assert 111 not in state._chats_cache
    assert 333 in state._chats_cache
    assert "ID: 333" in state.last_chats.split("\n")[0]


@pytest.mark.asyncio
async def test_on_private_message(aiogram_events, mock_bus):
    """Тест: личное сообщение генерирует правильный ивент."""
    msg = create_mock_message(12345, "private", "Привет", "Alex")

    await aiogram_events._on_private_message(msg)

    mock_bus.publish.assert_called_once_with(
        Events.AIOGRAM_MESSAGE_INCOMING,
        message="Привет",
        sender_name="Alex",
        chat_id=12345,
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

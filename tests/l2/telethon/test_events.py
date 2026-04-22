import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telethon.tl.types import UpdateMessageReactions
from src.utils.event.registry import Events
from tests.l2.telethon.conftest import async_generator


@pytest.mark.asyncio
async def test_update_state(telethon_events, mock_tg_client, state):
    dlg1 = MagicMock(
        is_user=True, is_group=False, is_channel=False, id=111, name="Иван", unread_count=1
    )
    dlg1.entity = MagicMock(username=None, bot=False, participants_count=None)

    dlg2 = MagicMock(
        is_user=False, is_group=True, is_channel=False, id=222, name="Dev Chat", unread_count=0
    )
    dlg2.entity = MagicMock(username="devchat", participants_count=42)

    mock_tg_client.client().iter_dialogs.return_value = async_generator([dlg1, dlg2])
    # Возвращаем пустой список сообщений для User, чтобы не крашился парсер в тесте
    mock_tg_client.client().get_messages.return_value = []

    await telethon_events._update_state()

    assert "[User]" in state.last_chats and "ID: 111" in state.last_chats
    assert "Group]" in state.last_chats and "ID: 222" in state.last_chats
    assert "Private" in state.last_chats or "Public" in state.last_chats


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.events.utils.get_display_name")
async def test_on_private_message(mock_get_display_name, telethon_events, mock_bus):
    mock_get_display_name.return_value = "Alex"
    event = MagicMock(chat_id=12345)
    event.get_chat = AsyncMock(return_value=MagicMock())

    # Явно указываем action=None, чтобы парсер не приклеил "[Системное сообщение]"
    event.message = MagicMock(
        id=42,
        text="Привет, агент!",
        fwd_from=None,
        reply_to=None,
        media=None,
        sender_id=None,
        action=None,
    )

    client_mock = telethon_events.tg_client.client()
    client_mock.iter_dialogs.return_value = async_generator([])
    # Заглушка для истории сообщений, чтобы не было краша
    client_mock.get_messages.return_value = []

    await telethon_events._on_private_message(event)

    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_MESSAGE_INCOMING,
        message="Привет, агент!",
        sender_name="Alex",
        chat_name="Alex",
        chat_id=12345,
        msg_id=42,
    )


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.events.utils.get_display_name")
async def test_on_group_message_mentioned(mock_get_display_name, telethon_events, mock_bus):
    mock_get_display_name.return_value = "Dev Chat"
    event = MagicMock(chat_id=-100999, mentioned=True)
    event.get_chat = AsyncMock(return_value=MagicMock())

    event.message = MagicMock(
        id=42,
        text="@agent, как дела?",
        fwd_from=None,
        reply_to=None,
        media=None,
        sender=None,
        sender_id=None,
        action=None,
    )

    client_mock = telethon_events.tg_client.client()
    client_mock.iter_dialogs.return_value = async_generator([])
    client_mock.get_messages.return_value = []

    await telethon_events._on_group_message(event)

    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_GROUP_MENTION,
        message="@agent, как дела?",
        sender_name="Unknown",
        chat_name="Dev Chat",
        chat_id=-100999,
        msg_id=42,
    )


@pytest.mark.asyncio
async def test_on_reaction(telethon_events, mock_bus):
    event = UpdateMessageReactions(peer=MagicMock(), msg_id=42, reactions=MagicMock())
    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_reaction(event)
    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_MESSAGE_REACTION,
        chat_id="Unknown",
        message_id=42,
        reactions="Реакции удалены",
    )

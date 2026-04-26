import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace


async def async_generator_helper(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_update_state(kurigram_events, mock_kurigram_client, state):
    dlg1 = SimpleNamespace(
        chat=SimpleNamespace(
            id=111,
            type="private",
            first_name="Иван",
            last_name="",
            username=None,
            is_bot=False,
            bio="",
        ),
        unread_messages_count=1,
    )

    dlg2 = SimpleNamespace(
        chat=SimpleNamespace(
            id=222,
            type="supergroup",
            title="Dev Chat",
            username="devchat",
            members_count=42,
            description="",
        ),
        unread_messages_count=0,
    )

    async def mock_get_dialogs(*args, **kwargs):
        yield dlg1
        yield dlg2

    client_mock = mock_kurigram_client.client()
    client_mock.get_dialogs = MagicMock(return_value=mock_get_dialogs())
    client_mock.get_chat_history = MagicMock(return_value=async_generator_helper([]))
    client_mock.get_chat = AsyncMock(return_value=SimpleNamespace(description=""))

    await kurigram_events._update_state(force=True)

    assert "[User]" in state.last_chats and "ID: 111" in state.last_chats
    assert "Group]" in state.last_chats and "ID: 222" in state.last_chats


@pytest.mark.asyncio
async def test_on_group_message_mentioned(kurigram_events, mock_bus):
    message = SimpleNamespace(
        id=42,
        chat=SimpleNamespace(id=-100999, type="supergroup", title="Dev Chat"),
        mentioned=True,
        text="@agent, как дела?",
        caption=None,
        service=False,
        photo=None,
        sticker=None,
        animation=None,
        voice=None,
        video=None,
        video_note=None,
        document=None,
        poll=None,
        media=None,
        forward_from=None,
        forward_from_chat=None,
        forward_sender_name=None,
        forward_date=None,
        reply_to_message=None,
        reply_to_message_id=None,
        message_thread_id=None,
        reply_to_top_message_id=None,
        from_user=None,
        sender_chat=None,
        reactions=None,
        reply_markup=None,
    )

    client_mock = kurigram_events.tg_client.client()
    client_mock.get_dialogs = MagicMock(return_value=async_generator_helper([]))
    client_mock.get_chat_history = MagicMock(return_value=async_generator_helper([]))

    await kurigram_events._on_group_message(client_mock, message)

    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args[1]
    assert call_args["chat_id"] == -100999
    assert call_args["message"] == "@agent, как дела?"

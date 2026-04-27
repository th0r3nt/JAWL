import pytest
from unittest.mock import AsyncMock, MagicMock, patch


async def async_generator_helper(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_update_state(telethon_events, mock_tg_client, state):
    dlg1 = MagicMock(
        is_user=True, is_group=False, is_channel=False, id=111, name="Иван", unread_count=1
    )
    # Явно указываем forum=False
    dlg1.entity = MagicMock(username=None, bot=False, participants_count=None, forum=False)

    dlg2 = MagicMock(
        is_user=False, is_group=True, is_channel=False, id=222, name="Dev Chat", unread_count=0
    )
    # Явно указываем forum=False
    dlg2.entity = MagicMock(username="devchat", participants_count=42, forum=False)

    async def mock_iter_dialogs(*args, **kwargs):
        yield dlg1
        yield dlg2

    client_mock = mock_tg_client.client()
    client_mock.iter_dialogs = mock_iter_dialogs
    # AsyncMock позволяет делать await
    client_mock.get_messages = AsyncMock(return_value=[])
    client_mock.get_dialogs = AsyncMock(return_value=MagicMock(total=2))

    await telethon_events._update_state(force=True)

    # Проверяем обновленный формат с бэктиками
    assert "[User]" in state.last_chats and "`111`" in state.last_chats
    assert "Group]" in state.last_chats and "`222`" in state.last_chats


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

    async def mock_iter_dialogs(*args, **kwargs):
        yield MagicMock()

    client_mock = telethon_events.tg_client.client()
    client_mock.iter_dialogs = mock_iter_dialogs
    client_mock.get_messages = AsyncMock(return_value=[])

    # ФИКС: Мокаем вспомогательный метод, чтобы он возвращал int, а не MagicMock
    telethon_events._get_unread_count = AsyncMock(return_value=2)

    await telethon_events._on_group_message(event)

    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args[1]
    assert call_args["chat_id"] == -100999
    assert call_args["message"] == "@agent, как дела?"

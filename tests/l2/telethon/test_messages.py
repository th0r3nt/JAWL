import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.l2_interfaces.telegram.telethon.skills.messages import TelethonMessages


@pytest.mark.asyncio
async def test_send_message_skill(mock_tg_client):
    skills = TelethonMessages(mock_tg_client)
    mock_tg_client.client().send_message = AsyncMock(return_value=MagicMock(id=999))
    res = await skills.send_message(to_id=123, text="Test")
    assert res.is_success is True
    mock_tg_client.client().send_message.assert_called_once_with(
        entity=123, message="Test", silent=False, parse_mode="md"
    )


@pytest.mark.asyncio
async def test_send_message_with_topic_skill(mock_tg_client):
    skills = TelethonMessages(mock_tg_client)
    mock_tg_client.client().send_message = AsyncMock(return_value=MagicMock(id=777))
    res = await skills.send_message(to_id=-100123, text="Test", topic_id=5238)
    assert res.is_success is True
    mock_tg_client.client().send_message.assert_called_once_with(
        entity=-100123, message="Test", silent=False, reply_to=5238, parse_mode="md"
    )


@pytest.mark.asyncio
async def test_messages_delete_message(mock_tg_client):
    skills = TelethonMessages(mock_tg_client)
    res = await skills.delete_message(msg_id=42, chat_id=123)
    assert res.is_success is True


@pytest.mark.asyncio
async def test_messages_edit_message(mock_tg_client):
    skills = TelethonMessages(mock_tg_client)
    res = await skills.edit_message(msg_id=42, new_text="Fixed", chat_id=123)
    assert res.is_success is True


@pytest.mark.asyncio
async def test_messages_click_inline_button(mock_tg_client):
    skills = TelethonMessages(mock_tg_client)
    mock_msg = MagicMock()
    mock_msg.buttons = [[MagicMock(text="Accept")]]
    mock_msg.click = AsyncMock(return_value=MagicMock(message="Success callback"))
    mock_tg_client.client().get_messages = AsyncMock(return_value=mock_msg)

    res = await skills.click_inline_button(chat_id=123, message_id=42, button_text="acc")
    assert res.is_success is True
    assert "Success callback" in res.message


@pytest.mark.asyncio
@patch(
    "src.l2_interfaces.telegram.telethon.utils._message_parser.TelethonMessageParser.build_string"
)
async def test_messages_search_messages(mock_build_string, mock_tg_client):
    mock_tg_client.timezone = 3
    skills = TelethonMessages(mock_tg_client)

    async def mock_search_gen(*args, **kwargs):
        for m in [MagicMock(id=1)]:
            yield m

    mock_tg_client.client().iter_messages = mock_search_gen
    mock_build_string.side_effect = ["Formatted 1"]
    res = await skills.search_messages(chat_id=123, query="test")
    assert res.is_success is True

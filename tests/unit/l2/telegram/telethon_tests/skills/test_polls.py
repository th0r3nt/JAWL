import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.l2_interfaces.telegram.telethon.skills.polls import TelethonPolls


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.skills.polls.Poll")
@patch("src.l2_interfaces.telegram.telethon.skills.polls.InputMediaPoll")
async def test_polls_create_poll(mock_input_media, mock_poll, mock_tg_client):
    skills = TelethonPolls(mock_tg_client)
    mock_sent_msg = MagicMock(id=888)
    mock_tg_client.client().send_message = AsyncMock(return_value=mock_sent_msg)

    res = await skills.create_poll(
        chat_id=123, question="Tea or Coffee?", options=["Tea", "Coffee"]
    )

    assert res.is_success is True, res.message
    assert "888" in res.message
    mock_tg_client.client().send_message.assert_called_once()


@pytest.mark.asyncio
async def test_polls_vote_in_poll(mock_tg_client):
    skills = TelethonPolls(mock_tg_client)

    mock_msg = MagicMock()
    mock_msg.poll.poll.closed = False
    mock_ans = MagicMock()
    mock_ans.option = b"1"
    mock_msg.poll.poll.answers = [mock_ans]

    mock_tg_client.client().get_messages = AsyncMock(return_value=mock_msg)
    mock_tg_client.client().get_input_entity = AsyncMock(return_value="entity")

    res = await skills.vote_in_poll(chat_id=123, message_id=42, option_indices=[0])

    assert res.is_success is True
    assert mock_tg_client.client().call_count >= 1
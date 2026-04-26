import pytest
from unittest.mock import AsyncMock, MagicMock

from src.l2_interfaces.telegram.kurigram.skills.polls import KurigramPolls


@pytest.mark.asyncio
async def test_polls_create_poll(mock_kurigram_client):
    skills = KurigramPolls(mock_kurigram_client)
    mock_sent_msg = MagicMock(id=888)
    mock_kurigram_client.client().send_poll = AsyncMock(return_value=mock_sent_msg)

    res = await skills.create_poll(
        chat_id=123, question="Tea or Coffee?", options=["Tea", "Coffee"]
    )

    assert res.is_success is True, res.message
    assert "888" in res.message
    mock_kurigram_client.client().send_poll.assert_called_once_with(
        chat_id=123, question="Tea or Coffee?", options=["Tea", "Coffee"]
    )


@pytest.mark.asyncio
async def test_polls_vote_in_poll(mock_kurigram_client):
    skills = KurigramPolls(mock_kurigram_client)

    mock_msg = MagicMock()
    mock_msg.poll.is_closed = False
    mock_msg.poll.options = [MagicMock(text="Tea"), MagicMock(text="Coffee")]

    mock_kurigram_client.client().get_messages = AsyncMock(return_value=mock_msg)

    res = await skills.vote_in_poll(chat_id=123, message_id=42, option_indices=[0])

    assert res.is_success is True
    mock_kurigram_client.client().vote_poll.assert_called_once_with(123, 42, [0])

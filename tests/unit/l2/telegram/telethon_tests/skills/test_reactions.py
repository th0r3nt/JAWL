import pytest

from src.l2_interfaces.telegram.telethon.skills.reactions import TelethonReactions


@pytest.mark.asyncio
async def test_reactions_set_reaction(mock_tg_client):
    skills = TelethonReactions(mock_tg_client)
    res = await skills.set_reaction(chat_id=123, message_id=42, reaction="👍")

    assert res.is_success is True
    assert mock_tg_client.client().call_count >= 1


@pytest.mark.asyncio
async def test_reactions_remove_reaction(mock_tg_client):
    skills = TelethonReactions(mock_tg_client)
    res = await skills.remove_reaction(chat_id=123, message_id=42)

    assert res.is_success is True
    assert mock_tg_client.client().call_count >= 1

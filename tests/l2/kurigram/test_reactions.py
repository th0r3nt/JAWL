import pytest

from src.l2_interfaces.telegram.kurigram.skills.reactions import KurigramReactions


@pytest.mark.asyncio
async def test_reactions_set_reaction(mock_kurigram_client):
    skills = KurigramReactions(mock_kurigram_client)
    res = await skills.set_reaction(chat_id=123, message_id=42, reaction="👍")

    assert res.is_success is True
    mock_kurigram_client.client().send_reaction.assert_called_once_with(
        chat_id=123, message_id=42, emoji="👍"
    )


@pytest.mark.asyncio
async def test_reactions_set_reaction_uses_kurigram_kwargs_for_string_ids(
    mock_kurigram_client,
):
    skills = KurigramReactions(mock_kurigram_client)

    res = await skills.set_reaction(chat_id="-100123", message_id="42", reaction="🔥")

    assert res.is_success is True
    assert mock_kurigram_client.client().send_reaction.call_args.kwargs == {
        "chat_id": -100123,
        "message_id": 42,
        "emoji": "🔥",
    }


@pytest.mark.asyncio
async def test_reactions_remove_reaction(mock_kurigram_client):
    skills = KurigramReactions(mock_kurigram_client)
    res = await skills.remove_reaction(chat_id=123, message_id=42)

    assert res.is_success is True
    mock_kurigram_client.client().send_reaction.assert_called_once_with(
        chat_id=123, message_id=42
    )


@pytest.mark.asyncio
async def test_reactions_remove_reaction_uses_empty_kurigram_reaction_kwargs(
    mock_kurigram_client,
):
    skills = KurigramReactions(mock_kurigram_client)

    res = await skills.remove_reaction(chat_id="-100123", message_id="42")

    assert res.is_success is True
    assert mock_kurigram_client.client().send_reaction.call_args.kwargs == {
        "chat_id": -100123,
        "message_id": 42,
    }

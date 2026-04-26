import pytest

from src.l2_interfaces.telegram.kurigram.skills.moderation import KurigramModeration


@pytest.mark.asyncio
async def test_moderation_ban_global(mock_kurigram_client):
    skills = KurigramModeration(mock_kurigram_client)
    res = await skills.ban_user(user_id=123)

    assert res.is_success is True
    assert "глобальный ЧС" in res.message


@pytest.mark.asyncio
async def test_moderation_ban_in_chat(mock_kurigram_client):
    skills = KurigramModeration(mock_kurigram_client)

    res = await skills.ban_user(user_id=123, chat_id=-100500)

    assert res.is_success is True
    assert "забанен в чате" in res.message
    mock_kurigram_client.client().ban_chat_member.assert_called_once_with(-100500, 123)


@pytest.mark.asyncio
async def test_moderation_kick_user(mock_kurigram_client):
    skills = KurigramModeration(mock_kurigram_client)

    res = await skills.kick_user(user_id=123, chat_id=-100500)

    assert res.is_success is True
    assert "выгнан (kick)" in res.message
    mock_kurigram_client.client().ban_chat_member.assert_called_once_with(-100500, 123)
    mock_kurigram_client.client().unban_chat_member.assert_called_once_with(-100500, 123)


@pytest.mark.asyncio
async def test_moderation_mute_user(mock_kurigram_client):
    skills = KurigramModeration(mock_kurigram_client)

    res = await skills.mute_user(user_id=123, chat_id=-100500, duration_minutes=60)

    assert res.is_success is True
    assert "замучен на 60 минут" in res.message

    call_args = mock_kurigram_client.client().restrict_chat_member.call_args
    assert call_args.args == (-100500, 123)
    assert call_args.kwargs["permissions"].can_send_messages is False
    assert call_args.kwargs["until_date"] is not None

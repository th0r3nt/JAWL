import pytest
from unittest.mock import AsyncMock

from src.l2_interfaces.telegram.telethon.skills.moderation import TelethonModeration


@pytest.mark.asyncio
async def test_moderation_ban_global(mock_tg_client):
    skills = TelethonModeration(mock_tg_client)
    res = await skills.ban_user(user_id=123)

    assert res.is_success is True
    assert "глобальный ЧС" in res.message


@pytest.mark.asyncio
async def test_moderation_ban_in_chat(mock_tg_client):
    skills = TelethonModeration(mock_tg_client)
    mock_tg_client.client().edit_permissions = AsyncMock()

    res = await skills.ban_user(user_id=123, chat_id=-100500)

    assert res.is_success is True
    assert "забанен в чате" in res.message
    mock_tg_client.client().edit_permissions.assert_called_once_with(
        -100500, 123, view_messages=False
    )


@pytest.mark.asyncio
async def test_moderation_kick_user(mock_tg_client):
    skills = TelethonModeration(mock_tg_client)
    mock_tg_client.client().kick_participant = AsyncMock()

    res = await skills.kick_user(user_id=123, chat_id=-100500)

    assert res.is_success is True
    assert "выгнан (kick)" in res.message
    mock_tg_client.client().kick_participant.assert_called_once_with(-100500, 123)


@pytest.mark.asyncio
async def test_moderation_mute_user(mock_tg_client):
    skills = TelethonModeration(mock_tg_client)
    mock_tg_client.client().edit_permissions = AsyncMock()

    res = await skills.mute_user(user_id=123, chat_id=-100500, duration_minutes=60)

    assert res.is_success is True
    assert "замучен на 60 минут" in res.message

    call_args = mock_tg_client.client().edit_permissions.call_args
    assert call_args[0] == (-100500, 123)
    assert call_args[1]["send_messages"] is False
    assert call_args[1]["until_date"] is not None

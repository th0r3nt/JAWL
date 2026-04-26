import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pyrogram import raw

from src.l2_interfaces.telegram.kurigram.skills.account import KurigramAccount


@pytest.mark.asyncio
async def test_account_change_username(mock_kurigram_client):
    skills = KurigramAccount(mock_kurigram_client)
    mock_kurigram_client.update_profile_state = AsyncMock()
    res = await skills.change_username(name="Neo", surname="Anderson")
    assert res.is_success is True
    assert "Neo Anderson" in res.message
    mock_kurigram_client.update_profile_state.assert_called_once()


@pytest.mark.asyncio
async def test_account_change_bio(mock_kurigram_client):
    skills = KurigramAccount(mock_kurigram_client)
    mock_kurigram_client.update_profile_state = AsyncMock()
    res = await skills.change_bio(text="Wake up, Neo")
    assert res.is_success is True


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.kurigram.skills.account.validate_sandbox_path")
async def test_account_change_avatar(mock_validate, mock_kurigram_client):
    skills = KurigramAccount(mock_kurigram_client)
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_validate.return_value = mock_path
    mock_kurigram_client.client().upload_file = AsyncMock(return_value="mocked_file")

    res = await skills.change_avatar(filepath="avatar.jpg")
    assert res.is_success is True


@pytest.mark.asyncio
async def test_account_add_contact(mock_kurigram_client):
    skills = KurigramAccount(mock_kurigram_client)
    res = await skills.add_contact(user_id="durov", first_name="Pavel", last_name="Durov")
    assert res.is_success is True


@pytest.mark.asyncio
async def test_account_get_user_info(mock_kurigram_client):
    skills = KurigramAccount(mock_kurigram_client)
    mock_full_user = MagicMock()
    mock_user = MagicMock(
        first_name="Pavel",
        last_name="Durov",
        username="durov",
        bot=False,
        restricted=False,
        scam=False,
        fake=False,
        status=None,
    )
    mock_full_user.users = [mock_user]
    mock_full_user.full_user.about = "Founder of Telegram"
    mock_kurigram_client.client().resolve_peer = AsyncMock(
        return_value=raw.types.InputPeerUser(user_id=123, access_hash=456)
    )
    mock_kurigram_client.client().invoke = AsyncMock(return_value=mock_full_user)

    res = await skills.get_user_info("durov")
    assert res.is_success is True
    assert "Pavel Durov" in res.message


@pytest.mark.asyncio
async def test_account_get_user_info_formats_raw_offline_timestamp(mock_kurigram_client):
    skills = KurigramAccount(mock_kurigram_client)
    mock_full_user = MagicMock()
    mock_user = MagicMock(
        first_name="Pavel",
        last_name="Durov",
        username="durov",
        bot=False,
        restricted=False,
        scam=False,
        fake=False,
        status=raw.types.UserStatusOffline(was_online=1_700_000_000),
    )
    mock_full_user.users = [mock_user]
    mock_full_user.full_user.about = ""
    mock_kurigram_client.client().resolve_peer = AsyncMock(
        return_value=raw.types.InputPeerUser(user_id=123, access_hash=456)
    )
    mock_kurigram_client.client().invoke = AsyncMock(return_value=mock_full_user)
    mock_kurigram_client.timezone = 3

    res = await skills.get_user_info("durov")

    assert res.is_success is True
    assert "Был(а) в сети: 2023-11-15 01:13:20" in res.message


@pytest.mark.asyncio
async def test_account_set_personal_channel(mock_kurigram_client):
    skills = KurigramAccount(mock_kurigram_client)
    mock_kurigram_client.update_profile_state = AsyncMock()
    mock_kurigram_client.client().resolve_peer = AsyncMock(
        return_value=raw.types.InputPeerChannel(channel_id=500, access_hash=600)
    )
    mock_kurigram_client.client().invoke = AsyncMock()

    res = await skills.set_personal_channel(channel_id="my_channel")
    assert res.is_success is True
    assert "установлен как личный" in res.message

    res_remove = await skills.set_personal_channel(channel_id="")
    assert res_remove.is_success is True
    assert mock_kurigram_client.update_profile_state.call_count == 2

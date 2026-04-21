import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.l2_interfaces.telegram.telethon.skills.account import TelethonAccount


@pytest.mark.asyncio
async def test_account_change_username(mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_tg_client.update_profile_state = AsyncMock()
    res = await skills.change_username(name="Neo", surname="Anderson")
    assert res.is_success is True
    assert "Neo Anderson" in res.message
    mock_tg_client.update_profile_state.assert_called_once()


@pytest.mark.asyncio
async def test_account_change_bio(mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_tg_client.update_profile_state = AsyncMock()
    res = await skills.change_bio(text="Wake up, Neo")
    assert res.is_success is True


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.skills.account.validate_sandbox_path")
async def test_account_change_avatar(mock_validate, mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_validate.return_value = mock_path
    mock_tg_client.client().upload_file = AsyncMock(return_value="mocked_file")

    res = await skills.change_avatar(filepath="avatar.jpg")
    assert res.is_success is True


@pytest.mark.asyncio
async def test_account_add_contact(mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_tg_client.client().get_input_entity = AsyncMock(return_value="mock_user")
    res = await skills.add_contact(user_id="durov", first_name="Pavel", last_name="Durov")
    assert res.is_success is True


@pytest.mark.asyncio
async def test_account_get_user_info(mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_full_user = MagicMock()
    mock_user = MagicMock(
        first_name="Pavel",
        last_name="Durov",
        username="durov",
        bot=False,
        restricted=False,
        scam=False,
    )
    mock_full_user.users = [mock_user]
    mock_full_user.full_user.about = "Founder of Telegram"
    mock_tg_client.client().side_effect = AsyncMock(return_value=mock_full_user)

    res = await skills.get_user_info("durov")
    assert res.is_success is True
    assert "Pavel Durov" in res.message


@pytest.mark.asyncio
async def test_account_set_personal_channel(mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_tg_client.update_profile_state = AsyncMock()
    mock_tg_client.client().get_input_entity = AsyncMock(return_value="mock_channel")
    mock_tg_client.client().side_effect = AsyncMock()

    res = await skills.set_personal_channel(channel_id="my_channel")
    assert res.is_success is True
    assert "установлен как личный" in res.message

    res_remove = await skills.set_personal_channel(channel_id="")
    assert res_remove.is_success is True
    assert mock_tg_client.update_profile_state.call_count == 2

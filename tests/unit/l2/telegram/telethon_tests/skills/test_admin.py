import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.l2_interfaces.telegram.telethon.skills.admin import TelethonAdmin


@pytest.mark.asyncio
async def test_admin_create_channel(mock_tg_client):
    skills = TelethonAdmin(mock_tg_client)

    mock_result = MagicMock()
    mock_result.chats = [MagicMock(id=999999)]
    mock_tg_client.client().side_effect = AsyncMock(return_value=mock_result)

    res = await skills.create_channel(title="JAWL Logs", is_megagroup=True)

    assert res.is_success is True
    assert "-100999999" in res.message


@pytest.mark.asyncio
async def test_admin_set_channel_username(mock_tg_client):
    """Тест: изменение юзернейма канала (публичный/приватный)."""
    skills = TelethonAdmin(mock_tg_client)
    mock_tg_client.client().side_effect = AsyncMock()

    # Делаем публичным
    res_public = await skills.set_channel_username(chat_id=-100500, username="lazy_exe")
    assert res_public.is_success is True
    assert "t.me/lazy_exe" in res_public.message

    # Делаем приватным
    res_private = await skills.set_channel_username(chat_id=-100500, username="")
    assert res_private.is_success is True
    assert "канал стал приватным" in res_private.message


@pytest.mark.asyncio
async def test_admin_pin_message(mock_tg_client):
    skills = TelethonAdmin(mock_tg_client)
    res = await skills.pin_message(chat_id=12345, message_id=42, notify=True)

    assert res.is_success is True
    mock_tg_client.client().pin_message.assert_called_once_with(
        entity=12345, message=42, notify=True
    )


@pytest.mark.asyncio
async def test_admin_promote_user(mock_tg_client):
    skills = TelethonAdmin(mock_tg_client)
    res = await skills.promote_user(chat_id=-100500, user_id=777, add_admins=False)

    assert res.is_success is True
    mock_tg_client.client().edit_admin.assert_called_once_with(
        entity=-100500,
        user=777,
        is_admin=True,
        change_info=True,
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        ban_users=True,
        invite_users=True,
        pin_messages=True,
        add_admins=False,
    )


@pytest.mark.asyncio
async def test_admin_demote_user(mock_tg_client):
    skills = TelethonAdmin(mock_tg_client)
    res = await skills.demote_user(chat_id=-100500, user_id=777)

    assert res.is_success is True
    mock_tg_client.client().edit_admin.assert_called_once_with(
        entity=-100500,
        user=777,
        is_admin=False,
    )


@pytest.mark.asyncio
async def test_admin_edit_chat_description(mock_tg_client):
    skills = TelethonAdmin(mock_tg_client)
    mock_tg_client.client().side_effect = AsyncMock()

    res = await skills.edit_chat_description(chat_id=-100500, new_description="New Bio")

    assert res.is_success is True
    assert "Описание чата успешно изменено" in res.message
    mock_tg_client.client().side_effect.assert_called_once()


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.skills.admin.validate_sandbox_path")
async def test_admin_edit_chat_avatar(mock_validate, mock_tg_client):
    skills = TelethonAdmin(mock_tg_client)

    mock_path = MagicMock()
    mock_path.name = "new_avatar.jpg"
    mock_path.is_file.return_value = True
    mock_validate.return_value = mock_path

    mock_tg_client.client().upload_file = AsyncMock(return_value="uploaded_photo_obj")

    from telethon.tl.types import InputPeerChannel

    mock_tg_client.client().get_input_entity = AsyncMock(
        return_value=InputPeerChannel(123, 456)
    )
    mock_tg_client.client().side_effect = AsyncMock()

    res = await skills.edit_chat_avatar(chat_id=-100500, filepath="new_avatar.jpg")

    assert res.is_success is True
    assert "Аватар чата успешно изменен" in res.message


@pytest.mark.asyncio
async def test_admin_create_topic(mock_tg_client):
    import src.l2_interfaces.telegram.telethon.skills.admin as admin_module

    if not admin_module.CreateForumTopicRequest:
        pytest.skip("Установленная версия Telethon не поддерживает CreateForumTopicRequest")

    skills = TelethonAdmin(mock_tg_client)

    mock_update = MagicMock()
    mock_update.message.id = 555
    mock_result = MagicMock()
    mock_result.updates = [mock_update]

    mock_tg_client.client().side_effect = AsyncMock(return_value=mock_result)

    res = await skills.create_topic(chat_id=-100500, title="Новый топик")

    assert res.is_success is True
    assert "ID топика: 555" in res.message

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.l2_interfaces.telegram.kurigram.skills.admin import KurigramAdmin


@pytest.mark.asyncio
async def test_admin_create_channel(mock_kurigram_client):
    skills = KurigramAdmin(mock_kurigram_client)

    mock_kurigram_client.client().create_supergroup = AsyncMock(return_value=MagicMock(id=999999))

    res = await skills.create_channel(title="JAWL Logs", is_megagroup=True)

    assert res.is_success is True
    assert "999999" in res.message


@pytest.mark.asyncio
async def test_admin_set_channel_username(mock_kurigram_client):
    """Изменение юзернейма канала: публичный и приватный режимы."""
    skills = KurigramAdmin(mock_kurigram_client)
    mock_kurigram_client.client().side_effect = AsyncMock()

    # Делаем публичным
    res_public = await skills.set_channel_username(chat_id=-100500, username="lazy_exe")
    assert res_public.is_success is True
    assert "t.me/lazy_exe" in res_public.message

    # Делаем приватным
    res_private = await skills.set_channel_username(chat_id=-100500, username="")
    assert res_private.is_success is True
    assert "канал стал приватным" in res_private.message


@pytest.mark.asyncio
async def test_admin_pin_message(mock_kurigram_client):
    skills = KurigramAdmin(mock_kurigram_client)
    res = await skills.pin_message(chat_id=12345, message_id=42, notify=True)

    assert res.is_success is True
    mock_kurigram_client.client().pin_chat_message.assert_called_once_with(
        12345, 42, disable_notification=False
    )


@pytest.mark.asyncio
async def test_admin_promote_user(mock_kurigram_client):
    skills = KurigramAdmin(mock_kurigram_client)
    res = await skills.promote_user(chat_id=-100500, user_id=777, add_admins=False)

    assert res.is_success is True
    call = mock_kurigram_client.client().promote_chat_member.call_args
    assert call.kwargs["chat_id"] == -100500
    assert call.kwargs["user_id"] == 777
    privileges = call.kwargs["privileges"]
    assert privileges.can_manage_chat is True
    assert privileges.can_change_info is True
    assert privileges.can_promote_members is False


@pytest.mark.asyncio
async def test_admin_demote_user(mock_kurigram_client):
    skills = KurigramAdmin(mock_kurigram_client)
    res = await skills.demote_user(chat_id=-100500, user_id=777)

    assert res.is_success is True
    call = mock_kurigram_client.client().promote_chat_member.call_args
    assert call.kwargs["chat_id"] == -100500
    assert call.kwargs["user_id"] == 777
    privileges = call.kwargs["privileges"]
    assert privileges.can_manage_chat is False
    assert privileges.can_promote_members is False


@pytest.mark.asyncio
async def test_admin_edit_chat_description(mock_kurigram_client):
    skills = KurigramAdmin(mock_kurigram_client)
    mock_kurigram_client.client().side_effect = AsyncMock()

    res = await skills.edit_chat_description(chat_id=-100500, new_description="New Bio")

    assert res.is_success is True
    assert "Описание чата успешно изменено" in res.message
    mock_kurigram_client.client().set_chat_description.assert_called_once_with(
        -100500, "New Bio"
    )


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.kurigram.skills.admin.validate_sandbox_path")
async def test_admin_edit_chat_avatar(mock_validate, mock_kurigram_client):
    skills = KurigramAdmin(mock_kurigram_client)

    mock_path = MagicMock()
    mock_path.name = "new_avatar.jpg"
    mock_path.is_file.return_value = True
    mock_validate.return_value = mock_path

    res = await skills.edit_chat_avatar(chat_id=-100500, filepath="new_avatar.jpg")

    assert res.is_success is True
    assert "Аватар чата успешно изменен" in res.message


@pytest.mark.asyncio
async def test_admin_create_topic(mock_kurigram_client):
    skills = KurigramAdmin(mock_kurigram_client)

    mock_kurigram_client.client().create_forum_topic = AsyncMock(return_value=MagicMock(id=555))

    res = await skills.create_topic(chat_id=-100500, title="Новый топик")

    assert res.is_success is True
    assert "ID топика: 555" in res.message

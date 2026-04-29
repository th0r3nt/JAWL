import pytest
from src.l2_interfaces.telegram.aiogram.skills.moderation import AiogramModeration


@pytest.mark.asyncio
async def test_moderation_ban(mock_client, mock_bot):
    """Тест: бан пользователя в группе."""
    skills = AiogramModeration(mock_client)

    res = await skills.ban_user(chat_id=-100500, user_id=42)

    assert res.is_success is True
    mock_bot.ban_chat_member.assert_called_once_with(chat_id=-100500, user_id=42)

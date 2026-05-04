import pytest
from unittest.mock import MagicMock
from src.l2_interfaces.telegram.aiogram.skills.messages import AiogramMessages


@pytest.mark.asyncio
async def test_messages_send(mock_client, mock_bot):
    """Тест: успешная отправка сообщения."""
    skills = AiogramMessages(mock_client)

    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 777
    mock_bot.send_message.return_value = mock_sent_msg

    res = await skills.send_message(chat_id=123, text="Test")

    assert res.is_success is True
    assert "777" in res.message
    mock_bot.send_message.assert_called_once_with(
        chat_id=123, text="Test", reply_to_message_id=None
    )

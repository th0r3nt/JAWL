import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.l2_interfaces.telegram.telethon.skills.chats import TelethonChats


@pytest.mark.asyncio
async def test_chats_mark_as_read(mock_tg_client):
    skills = TelethonChats(mock_tg_client)
    mock_tg_client.client().get_entity = AsyncMock(return_value="mock_entity")

    res = await skills.mark_as_read(chat_id=123)
    assert res.is_success is True
    assert mock_tg_client.client().send_read_acknowledge.call_count >= 1


@pytest.mark.asyncio
async def test_chats_join_chat(mock_tg_client):
    skills = TelethonChats(mock_tg_client)

    # 1. По юзернейму
    res_username = await skills.join_chat("durov")
    assert res_username.is_success is True

    # 2. По приватной ссылке
    res_link = await skills.join_chat("https://t.me/joinchat/AAAAAE")
    assert res_link.is_success is True


@pytest.mark.asyncio
async def test_chats_read_chat_complex_parsing(mock_tg_client):
    """Тест: сложное чтение чата со всеми медиа, реплаями и реакциями."""
    skills = TelethonChats(mock_tg_client)
    mock_tg_client.timezone = 3

    mock_msg = MagicMock()
    mock_msg.id = 1
    mock_msg.date = datetime(2023, 10, 10, 15, 0, tzinfo=timezone.utc)
    mock_msg.action = None
    mock_msg.out = False

    mock_sender = MagicMock()
    mock_sender.first_name = "Th0r3nt"
    mock_msg.sender = mock_sender
    mock_msg.sender_id = 999

    mock_msg.text = "Смотри мем"
    mock_msg.photo = True

    mock_fwd = MagicMock()
    mock_fwd.from_name = "Meme Channel"
    mock_msg.fwd_from = mock_fwd
    mock_msg.get_forward_sender = AsyncMock(return_value=None)

    mock_reply = MagicMock()
    mock_reply.reply_to_msg_id = 42
    mock_reply.forum_topic = False
    mock_msg.reply_to = mock_reply

    mock_reaction = MagicMock()
    mock_reaction.reaction.emoticon = "🔥"
    mock_reaction.count = 5
    mock_msg.reactions.results = [mock_reaction]

    # Отключаем recent_reactions, чтобы отработал блок results
    mock_msg.reactions.recent_reactions = None

    mock_btn = MagicMock()
    mock_btn.text = "Лайк"
    mock_msg.buttons = [[mock_btn]]

    async def async_generator(items):
        for item in items:
            yield item

    mock_tg_client.client().iter_messages = MagicMock(return_value=async_generator([mock_msg]))
    mock_tg_client.client().get_entity = AsyncMock(return_value="mock_entity")
    mock_tg_client.client().get_messages = AsyncMock(return_value=None)

    res = await skills.read_chat(chat_id=123, limit=1)

    assert res.is_success is True, res.message
    assert "[Фотография] Смотри мем" in res.message
    assert "[Переслано от: Meme Channel]" in res.message
    assert "(В ответ на сообщение ID 42 от Unknown)" in res.message
    assert "[Реакции: 🔥 x5]" in res.message
    assert "[Кнопки: [Лайк]]" in res.message

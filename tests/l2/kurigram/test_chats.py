import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.l2_interfaces.telegram.kurigram.skills.chats import KurigramChats


@pytest.mark.asyncio
async def test_chats_mark_as_read(mock_kurigram_client):
    skills = KurigramChats(mock_kurigram_client)
    mock_kurigram_client.client().get_chat = AsyncMock(
        return_value=MagicMock(id=123, type="supergroup", is_forum=False)
    )
    mock_kurigram_client.client().resolve_peer = AsyncMock(return_value=MagicMock())

    res = await skills.mark_as_read(chat_id=123)
    assert res.is_success is True
    mock_kurigram_client.client().read_chat_history.assert_called_once_with(123)


@pytest.mark.asyncio
async def test_chats_join_chat(mock_kurigram_client):
    skills = KurigramChats(mock_kurigram_client)

    # 1. По юзернейму
    res_username = await skills.join_chat("durov")
    assert res_username.is_success is True

    # 2. По приватной ссылке
    res_link = await skills.join_chat("https://t.me/joinchat/AAAAAE")
    assert res_link.is_success is True


@pytest.mark.asyncio
async def test_chats_read_chat_complex_parsing(mock_kurigram_client):
    """Сложное чтение чата со всеми медиа, реплаями и реакциями."""
    skills = KurigramChats(mock_kurigram_client)
    mock_kurigram_client.timezone = 3

    mock_msg = MagicMock()
    mock_msg.id = 1
    mock_msg.date = datetime(2023, 10, 10, 15, 0, tzinfo=timezone.utc)
    mock_msg.outgoing = False
    mock_msg.service = None
    mock_msg.message_thread_id = None

    mock_sender = MagicMock()
    mock_sender.first_name = "Th0r3nt"
    mock_sender.last_name = ""
    mock_sender.id = 999
    mock_msg.from_user = mock_sender

    mock_msg.text = "Смотри мем"
    mock_msg.caption = None
    mock_msg.photo = True

    mock_msg.forward_origin = None
    mock_msg.forward_from = None
    mock_msg.forward_from_chat = None
    mock_msg.forward_sender_name = "Meme Channel"
    mock_msg.reply_to_message_id = 42
    mock_msg.reply_to_top_message_id = None

    mock_reaction = MagicMock()
    mock_reaction.reaction.emoticon = "🔥"
    mock_reaction.emoji = None
    mock_reaction.count = 5
    mock_msg.reactions.reactions = None
    mock_msg.reactions.results = [mock_reaction]

    mock_btn = MagicMock()
    mock_btn.text = "Лайк"
    mock_msg.reply_markup.inline_keyboard = [[mock_btn]]

    async def async_generator(items):
        for item in items:
            yield item

    mock_kurigram_client.client().get_chat = AsyncMock(
        return_value=MagicMock(id=123, type="supergroup", title="Dev Chat")
    )
    mock_kurigram_client.client().get_chat_history = MagicMock(
        return_value=async_generator([mock_msg])
    )
    mock_kurigram_client.client().get_dialogs = MagicMock(return_value=async_generator([]))
    mock_kurigram_client.client().get_messages = AsyncMock(return_value=None)

    res = await skills.read_chat(chat_id=123, limit=1)

    assert res.is_success is True, res.message
    assert "[Фотография] Смотри мем" in res.message
    assert "[Переслано от: Meme Channel]" in res.message
    assert "(В ответ на сообщение ID 42)" in res.message
    assert "[Реакции: 🔥 x5]" in res.message
    assert "[Кнопки: [Лайк]]" in res.message

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from datetime import datetime
from pyrogram import raw
from pyrogram.enums import ParseMode
from pyrogram.types import ReplyParameters

import src.l2_interfaces.telegram.kurigram.skills.messages as messages_module
from src.l2_interfaces.telegram.kurigram.skills.messages import KurigramMessages


@pytest.mark.asyncio
async def test_send_message_skill(mock_kurigram_client):
    skills = KurigramMessages(mock_kurigram_client)
    mock_kurigram_client.client().send_message = AsyncMock(return_value=MagicMock(id=999))
    res = await skills.send_message(to_id=123, text="Test")
    assert res.is_success is True
    mock_kurigram_client.client().send_message.assert_called_once_with(
        chat_id=123,
        text="Test",
        disable_notification=False,
        parse_mode=ParseMode.MARKDOWN,
    )


@pytest.mark.asyncio
async def test_send_message_with_topic_skill(mock_kurigram_client):
    skills = KurigramMessages(mock_kurigram_client)
    mock_kurigram_client.client().send_message = AsyncMock(return_value=MagicMock(id=777))
    res = await skills.send_message(to_id=-100123, text="Test", topic_id=5238)
    assert res.is_success is True
    mock_kurigram_client.client().send_message.assert_called_once_with(
        chat_id=-100123,
        text="Test",
        disable_notification=False,
        parse_mode=ParseMode.MARKDOWN,
        message_thread_id=5238,
    )


@pytest.mark.asyncio
async def test_send_message_uses_kurigram_reply_silent_and_schedule_kwargs(
    mock_kurigram_client, monkeypatch
):
    class FixedDatetime:
        @classmethod
        def now(cls):
            return datetime(2026, 1, 1, 12, 0, 0)

    monkeypatch.setattr(messages_module, "datetime", FixedDatetime)

    skills = KurigramMessages(mock_kurigram_client)
    mock_kurigram_client.client().send_message = AsyncMock(return_value=MagicMock(id=321))

    res = await skills.send_message(
        to_id="durov",
        text="Scheduled reply",
        reply_to_message_id=42,
        topic_id=5238,
        is_silent=True,
        time_delay=2,
    )

    assert res.is_success is True
    mock_kurigram_client.client().send_message.assert_called_once_with(
        chat_id="durov",
        text="Scheduled reply",
        disable_notification=True,
        parse_mode=ParseMode.MARKDOWN,
        reply_parameters=ReplyParameters(message_id=42),
        schedule_date=datetime(2026, 1, 1, 12, 0, 10),
    )


@pytest.mark.asyncio
async def test_messages_delete_message(mock_kurigram_client):
    skills = KurigramMessages(mock_kurigram_client)
    res = await skills.delete_message(msg_id=42, chat_id=123)
    assert res.is_success is True


@pytest.mark.asyncio
async def test_messages_edit_message(mock_kurigram_client):
    skills = KurigramMessages(mock_kurigram_client)
    res = await skills.edit_message(msg_id=42, new_text="Fixed", chat_id=123)
    assert res.is_success is True


@pytest.mark.asyncio
async def test_messages_click_inline_button(mock_kurigram_client):
    skills = KurigramMessages(mock_kurigram_client)
    mock_msg = MagicMock()
    mock_msg.reply_markup = SimpleNamespace(
        inline_keyboard=[[SimpleNamespace(text="Accept")]]
    )
    mock_msg.click = AsyncMock(return_value=MagicMock(message="Success callback"))
    mock_kurigram_client.client().get_messages = AsyncMock(return_value=mock_msg)

    res = await skills.click_inline_button(chat_id=123, message_id=42, button_text="acc")
    assert res.is_success is True
    assert "Success callback" in res.message


@pytest.mark.asyncio
async def test_messages_search_messages(mock_kurigram_client):
    mock_kurigram_client.timezone = 3
    skills = KurigramMessages(mock_kurigram_client)

    async def mock_search_gen(*args, **kwargs):
        msg = MagicMock(id=1)
        msg.from_user = None
        msg.sender_chat = None
        msg.text = "Formatted 1"
        msg.caption = None
        msg.media = None
        msg.service = None
        msg.forward_origin = None
        msg.forward_from = None
        msg.forward_from_chat = None
        msg.forward_sender_name = None
        msg.reply_to_message = None
        msg.date = None
        yield msg

    mock_kurigram_client.client().search_messages = mock_search_gen
    res = await skills.search_messages(chat_id=123, query="test")
    assert res.is_success is True


@pytest.mark.asyncio
async def test_messages_edit_draft(mock_kurigram_client):
    skills = KurigramMessages(mock_kurigram_client)

    target_peer = raw.types.InputPeerUser(user_id=123, access_hash=456)
    mock_kurigram_client.client().resolve_peer = AsyncMock(return_value=target_peer)

    mock_draft = MagicMock()
    mock_draft.peer = target_peer
    mock_draft.draft.message = "Первый абзац"
    mock_kurigram_client.client().invoke = AsyncMock(
        side_effect=[MagicMock(updates=[mock_draft]), None]
    )

    res = await skills.edit_draft(chat_id=123, text="Второй абзац", append=True)

    assert res.is_success is True
    save_call = mock_kurigram_client.client().invoke.call_args_list[-1].args[0]
    assert save_call.peer == target_peer
    assert save_call.message == "Первый абзац\n\nВторой абзац"

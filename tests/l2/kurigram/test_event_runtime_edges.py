from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.l2_interfaces.telegram.kurigram.utils._message_parser import (
    KurigramMessageParser,
)
from src.utils.event.registry import Events


async def async_generator(items):
    for item in items:
        yield item


def message_stub(**overrides):
    base = {
        "id": None,
        "message_id": None,
        "date": datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        "text": "",
        "caption": None,
        "message": None,
        "raw_text": None,
        "from_user": None,
        "sender": None,
        "sender_chat": None,
        "chat": SimpleNamespace(id=-100123, type="supergroup", title="Runtime Chat"),
        "is_group": True,
        "is_channel": False,
        "out": False,
        "outgoing": False,
        "service": False,
        "action": None,
        "media": None,
        "photo": None,
        "sticker": None,
        "animation": None,
        "gif": None,
        "voice": None,
        "video": None,
        "video_note": None,
        "document": None,
        "poll": None,
        "audio": None,
        "forward_origin": None,
        "forward_from": None,
        "forward_from_chat": None,
        "forward_sender_name": None,
        "forward_date": None,
        "forward_from_message_id": None,
        "forward_signature": None,
        "fwd_from": None,
        "reply_to_message": None,
        "reply_to_message_id": None,
        "reply_to": None,
        "message_thread_id": None,
        "reply_to_top_message_id": None,
        "reactions": None,
        "reply_markup": None,
        "buttons": None,
        "entities": [],
        "caption_entities": [],
        "mentioned": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class MessageWithForwardOriginOnly:
    id = 1
    message_id = None
    date = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    text = "forwarded"
    caption = None
    message = None
    raw_text = None
    from_user = SimpleNamespace(id=7, first_name="Sender", last_name="")
    sender = None
    sender_chat = None
    chat = SimpleNamespace(id=-100123, type="supergroup", title="Runtime Chat")
    is_group = True
    is_channel = False
    out = False
    outgoing = False
    service = False
    action = None
    media = None
    photo = None
    sticker = None
    animation = None
    gif = None
    voice = None
    video = None
    video_note = None
    document = None
    poll = None
    audio = None
    fwd_from = None
    forward_origin = SimpleNamespace(
        sender_user=SimpleNamespace(id=42, first_name="Origin", last_name=""),
        sender_user_name=None,
        chat=None,
        sender_chat=None,
        date=datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc),
    )
    reply_to_message = None
    reply_to_message_id = None
    reply_to = None
    message_thread_id = None
    reply_to_top_message_id = None
    reactions = None
    reply_markup = None
    buttons = None
    entities = []
    caption_entities = []
    mentioned = False

    @property
    def forward_from(self):
        raise AssertionError("deprecated forward_from was accessed")

    @property
    def forward_from_chat(self):
        raise AssertionError("deprecated forward_from_chat was accessed")

    @property
    def forward_sender_name(self):
        raise AssertionError("deprecated forward_sender_name was accessed")

    @property
    def forward_date(self):
        raise AssertionError("deprecated forward_date was accessed")

    @property
    def forward_from_message_id(self):
        raise AssertionError("deprecated forward_from_message_id was accessed")

    @property
    def forward_signature(self):
        raise AssertionError("deprecated forward_signature was accessed")


@pytest.mark.asyncio
async def test_raw_like_reaction_update_publishes_reaction_payload(kurigram_events, mock_bus):
    class UpdateMessageReactions:
        pass

    update = UpdateMessageReactions()
    update.peer = SimpleNamespace(channel_id=12345)
    update.msg_id = 77
    update.reactions = SimpleNamespace(
        results=[
            SimpleNamespace(reaction=SimpleNamespace(emoticon="🔥"), count=3),
            SimpleNamespace(reaction=SimpleNamespace(document_id=999), count=None),
        ]
    )

    await kurigram_events._on_reaction(kurigram_events.tg_client.client(), update)

    mock_bus.publish.assert_called_once_with(
        Events.KURIGRAM_MESSAGE_REACTION,
        chat_id=-1000000012345,
        message_id=77,
        reactions="🔥 x3, [CustomEmoji]",
    )


@pytest.mark.asyncio
async def test_mention_detection_handles_boundaries_text_mention_and_reply_to_me(
    kurigram_events,
):
    kurigram_events._me = SimpleNamespace(id=7, username="agent")

    assert await kurigram_events._is_mentioned(message_stub(text="ping @agent")) is True
    assert await kurigram_events._is_mentioned(message_stub(text="ping @agent_bot")) is False
    assert await kurigram_events._is_mentioned(message_stub(text="mail agent@agent.test")) is False

    text_mention = message_stub(
        text="hidden mention",
        entities=[SimpleNamespace(user=SimpleNamespace(id=7))],
    )
    assert await kurigram_events._is_mentioned(text_mention) is True

    reply_to_me = message_stub(
        text="reply",
        reply_to_message=message_stub(from_user=SimpleNamespace(id=7, first_name="Agent")),
    )
    assert await kurigram_events._is_mentioned(reply_to_me) is True


@pytest.mark.asyncio
async def test_recent_history_excludes_current_message(kurigram_events, mock_kurigram_client):
    current = message_stub(id=10, text="current")
    previous = message_stub(id=9, text="previous")
    older = message_stub(id=8, text="older")
    mock_kurigram_client.client().get_chat_history = MagicMock(
        return_value=async_generator([current, previous, older])
    )

    history = await kurigram_events._fetch_recent_history(
        chat_id=-100123,
        limit=2,
        current_msg_id=10,
    )

    assert "[ID: 10]" not in history
    assert "[ID: 8]" in history
    assert "[ID: 9]" in history
    assert "older" in history
    assert "previous" in history


@pytest.mark.asyncio
async def test_forward_origin_parsing_avoids_deprecated_message_properties(
    kurigram_events, mock_kurigram_client
):
    msg = MessageWithForwardOriginOnly()

    parser_result = await KurigramMessageParser.build_string(
        mock_kurigram_client.client(),
        msg.chat.id,
        msg,
        timezone=3,
    )
    event_result = await kurigram_events._build_message_string(
        mock_kurigram_client.client(),
        msg.chat.id,
        msg,
    )

    assert "Переслано от: Origin" in parser_result
    assert "Переслано от: Origin" in event_result


@pytest.mark.asyncio
async def test_message_parser_builds_media_forward_reply_and_buttons_from_dummy_objects():
    client = SimpleNamespace()
    client.get_messages = AsyncMock(
        return_value=message_stub(
            id=41,
            text="original",
            from_user=SimpleNamespace(id=501, first_name="Reply", last_name="Author"),
        )
    )

    msg = message_stub(
        id=42,
        text="see attached",
        photo=object(),
        forward_origin=SimpleNamespace(sender_chat=SimpleNamespace(title="News Desk")),
        reply_to=SimpleNamespace(reply_to_msg_id=41),
        reply_markup=SimpleNamespace(
            inline_keyboard=[
                [
                    SimpleNamespace(text="Open"),
                    SimpleNamespace(text="Details"),
                ]
            ]
        ),
        from_user=SimpleNamespace(id=500, first_name="Runtime", last_name="User"),
    )

    result = await KurigramMessageParser.build_string(
        client=client,
        target_entity=-100123,
        msg=msg,
        timezone=3,
    )

    assert "[Фотография] see attached" in result
    assert "[Переслано от: News Desk]" in result
    assert "(В ответ на сообщение ID 41 от Reply Author (ID: 501))" in result
    assert "[Кнопки: [Open], [Details]]" in result
    client.get_messages.assert_awaited_once_with(-100123, message_ids=41)

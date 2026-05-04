import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.l2_interfaces.telegram.telethon.utils._message_parser import TelethonMessageParser


@pytest.mark.asyncio
async def test_parse_media():
    """Тест: правильное определение типа медиа в Telegram."""
    msg = MagicMock()
    msg.action = None
    msg.media = True

    # Имитируем фото
    msg.photo = True
    msg.document = False
    assert TelethonMessageParser.parse_media(msg) == "[Фотография]"

    # Имитируем файл
    msg.photo = False
    msg.sticker = False
    msg.gif = False
    msg.voice = False
    msg.video = False
    msg.video_note = False
    msg.document = True

    assert TelethonMessageParser.parse_media(msg) == "[Файл]"


@pytest.mark.asyncio
async def test_build_string_full():
    """Тест: полная сборка сложного сообщения (текст + медиа + время + автор)."""
    client = MagicMock()
    target_entity = MagicMock()
    msg = MagicMock()

    msg.id = 42
    msg.out = False
    msg.date = MagicMock()
    msg.date.timestamp = MagicMock(return_value=1700000000)  # Нужно для format_datetime

    # Мокаем методы парсера через patch, чтобы не проверять всё сразу
    with pytest.MonkeyPatch.context() as m:
        m.setattr(TelethonMessageParser, "get_sender_name", AsyncMock(return_value="Alex"))
        m.setattr(
            TelethonMessageParser, "determine_reply", MagicMock(return_value=(False, None))
        )
        m.setattr(TelethonMessageParser, "parse_media", MagicMock(return_value="[Фотография]"))
        m.setattr(TelethonMessageParser, "parse_forward", AsyncMock(return_value=""))
        m.setattr(TelethonMessageParser, "parse_reply", AsyncMock(return_value=""))
        m.setattr(TelethonMessageParser, "parse_reactions", AsyncMock(return_value=""))
        m.setattr(TelethonMessageParser, "parse_buttons", MagicMock(return_value=""))

        msg.text = "Смотри!"

        result = await TelethonMessageParser.build_string(
            client, target_entity, msg, timezone=3, read_outbox_max_id=0
        )

        # Ожидаемый формат: [Время] [ID: 42] [Не прочитано] Alex: [Фотография] Смотри!
        assert "[ID: 42]" in result
        assert "Alex:" in result
        assert "[Фотография] Смотри!" in result


def test_determine_reply():
    """Тест: корректное разрешение конфликтов между Reply_to и Forum Topics."""
    # 1. Обычный реплай в ЛС/группе
    msg_normal = MagicMock()
    msg_normal.reply_to.forum_topic = False
    msg_normal.reply_to.reply_to_msg_id = 150

    is_reply, reply_id = TelethonMessageParser.determine_reply(msg_normal, topic_id=None)
    assert is_reply is True
    assert reply_id == 150

    # 2. Сообщение внутри топика (это НЕ ответ пользователю, а принадлежность к топику)
    msg_topic_base = MagicMock()
    msg_topic_base.reply_to.forum_topic = True
    msg_topic_base.reply_to.reply_to_top_id = None
    msg_topic_base.reply_to.reply_to_msg_id = 99  # ID самого топика

    is_reply, reply_id = TelethonMessageParser.determine_reply(msg_topic_base, topic_id=99)
    assert is_reply is False  # Парсер должен понять, что это не реплай

    # 3. Реальный реплай внутри топика
    msg_topic_reply = MagicMock()
    msg_topic_reply.reply_to.forum_topic = True
    msg_topic_reply.reply_to.reply_to_top_id = 99  # ID топика
    msg_topic_reply.reply_to.reply_to_msg_id = 150  # ID сообщения, на которое ответили

    is_reply, reply_id = TelethonMessageParser.determine_reply(msg_topic_reply, topic_id=99)
    assert is_reply is True
    assert reply_id == 150


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.utils._message_parser.utils.get_display_name")
async def test_parse_reactions(mock_get_display_name):
    """Тест: парсер корректно извлекает реакции в разных форматах Telethon API."""
    client = AsyncMock()
    mock_get_display_name.return_value = "Th0r3nt"

    # 1. Формат recent_reactions (когда мы получаем новые события)
    msg_recent = MagicMock()
    reaction_obj = MagicMock()
    reaction_obj.reaction.emoticon = "🔥"
    reaction_obj.peer_id = 12345
    msg_recent.reactions.recent_reactions = [reaction_obj]
    msg_recent.reactions.results = None

    client.get_entity.return_value = MagicMock()

    res_recent = await TelethonMessageParser.parse_reactions(client, msg_recent)
    assert "[Реакции: 🔥 от Th0r3nt]" in res_recent

    # 2. Формат results (когда мы вытягиваем историю через get_messages)
    msg_results = MagicMock()
    msg_results.reactions.recent_reactions = None

    res_obj1 = MagicMock()
    res_obj1.reaction.emoticon = "👍"
    res_obj1.count = 10

    res_obj2 = MagicMock()
    res_obj2.reaction.emoticon = "👎"
    res_obj2.count = 2

    msg_results.reactions.results = [res_obj1, res_obj2]

    res_history = await TelethonMessageParser.parse_reactions(client, msg_results)
    assert "[Реакции: 👍 x10, 👎 x2]" in res_history

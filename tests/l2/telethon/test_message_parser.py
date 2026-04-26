import pytest
from unittest.mock import AsyncMock, MagicMock
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

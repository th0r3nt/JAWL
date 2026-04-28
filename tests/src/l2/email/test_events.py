import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.utils.event.registry import Events
from src.l2_interfaces.email.events import EmailEvents


@pytest.fixture
def email_events(mock_email_client, email_state):
    bus = MagicMock()
    bus.publish = AsyncMock()
    return EmailEvents(mock_email_client, email_state, bus, interval_sec=10)


def test_check_new_emails_success(email_events):
    """Тест: парсинг новых писем и дедупликация по UID."""
    mock_mail = MagicMock()

    # Имитируем два непрочитанных письма: 101 и 102
    # Так как 101 мы заранее добавим в "прочитанные" в кэш агента,
    # fetch вызовется ТОЛЬКО для 102. Поэтому мок должен содержать 2 элемента.
    mock_mail.uid.side_effect = [
        ("OK", [b"101 102"]),  # 1. Ответ на search UNSEEN
        ("OK", [[b"", b"Subject: Hello\r\nFrom: User <u@m.com>"]]),  # 2. Ответ на fetch 102
    ]
    email_events.client.imap_connection.return_value.__enter__.return_value = mock_mail

    # Устанавливаем 101 как уже обработанное
    email_events._seen_uids.add("101")

    new_emails = email_events._check_new_emails()

    # Должен вернуть только 102
    assert len(new_emails) == 1
    assert new_emails[0]["uid"] == "102"
    assert new_emails[0]["subject"] == "Hello"
    assert "User" in new_emails[0]["sender"]
    assert "102" in email_events._seen_uids


@pytest.mark.asyncio
async def test_events_loop_publishes_to_bus(email_events):
    """Тест: цикл поллинга публикует события в шину."""
    email_events._is_running = True

    # Мокаем проверку так, чтобы она вернула одно новое письмо
    email_events._check_new_emails = MagicMock(
        return_value=[{"uid": "99", "subject": "Alert", "sender": "System"}]
    )

    # Имитируем asyncio.sleep для выхода из цикла
    async def fake_sleep(*args, **kwargs):
        email_events._is_running = False

    with patch("asyncio.sleep", side_effect=fake_sleep):
        await email_events._loop()

    email_events.bus.publish.assert_called_once_with(
        Events.EMAIL_INCOMING,
        uid="99",
        sender_name="System",
        message="Новое письмо. Тема: Alert",
    )

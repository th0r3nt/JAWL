import pytest
from unittest.mock import MagicMock
from src.l2_interfaces.email.skills.mail import EmailSkills


@pytest.mark.asyncio
async def test_email_send_message(mock_email_client):
    """Тест: успешная отправка письма."""
    skills = EmailSkills(mock_email_client)

    mock_server = MagicMock()
    # Настраиваем контекстный менеджер
    mock_email_client.smtp_connection.return_value.__enter__.return_value = mock_server

    res = await skills.send_email("boss@mail.com", "Report", "All systems operational.")

    assert res.is_success is True
    mock_server.send_message.assert_called_once()

    # Проверяем, что сформировалось правильное сообщение
    sent_msg = mock_server.send_message.call_args[0][0]
    assert sent_msg["Subject"] == "Report"
    assert sent_msg["To"] == "boss@mail.com"


@pytest.mark.asyncio
async def test_email_delete_message(mock_email_client):
    """Тест: удаление письма по UID."""
    skills = EmailSkills(mock_email_client)

    mock_mail = MagicMock()
    mock_email_client.imap_connection.return_value.__enter__.return_value = mock_mail
    mock_email_client.update_state_view = MagicMock()

    res = await skills.delete_email(uid=42)

    assert res.is_success is True

    # Проверяем, что проставился флаг \Deleted и вызван expunge
    mock_mail.uid.assert_called_with("STORE", b"42", "+FLAGS", "(\\Deleted)")
    mock_mail.expunge.assert_called_once()

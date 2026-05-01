import pytest
from unittest.mock import patch, MagicMock
from src.l2_interfaces.email.client import EmailClient


@pytest.mark.asyncio
@patch("src.l2_interfaces.email.client.imaplib.IMAP4_SSL")
async def test_email_client_start_success(mock_imap, email_state):
    """Тест: определение серверов и успешный логин."""
    client = EmailClient(state=email_state, account="test@yandex.ru", password="pwd")

    mock_mail_instance = MagicMock()
    mock_imap.return_value = mock_mail_instance

    # Имитируем отключение реального обновления UI, чтобы не усложнять тест
    with patch.object(client, "update_state_view"):
        await client.start()

    assert client.imap_server == "imap.yandex.ru"
    assert client.state.is_online is True
    mock_mail_instance.login.assert_called_once_with("test@yandex.ru", "pwd")


@pytest.mark.asyncio
async def test_email_client_start_unknown_domain() -> None:
    """
    Проверяет поведение клиента при попытке подключиться к неизвестному
    почтовому провайдеру (домену). Клиент не должен падать, сервера
    должны остаться пустыми строками, а статус - Offline.
    """
    from src.l0_state.interfaces.email_state import EmailState
    from src.l2_interfaces.email.client import EmailClient

    state = EmailState()
    client = EmailClient(state=state, account="test@unknown-domain.xyz", password="123")

    await client.start()

    #Клиент инициализирует эти поля пустой строкой `""`, а не `None`
    assert client.imap_server == ""
    assert client.smtp_server == ""
    assert client.state.is_online is False

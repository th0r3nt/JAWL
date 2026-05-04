import pytest
from unittest.mock import MagicMock
from src.l2_interfaces.email.state import EmailState
from src.l2_interfaces.email.client import EmailClient


@pytest.fixture
def email_state():
    return EmailState(recent_limit=5)


@pytest.fixture
def mock_email_client(email_state):
    """Клиент с моками контекстных менеджеров IMAP и SMTP."""
    client = EmailClient(state=email_state, account="agent@gmail.com", password="pwd")
    client.imap_server = "imap.gmail.com"
    client.smtp_server = "smtp.gmail.com"

    # Мокаем контекстные менеджеры напрямую
    client.imap_connection = MagicMock()
    client.smtp_connection = MagicMock()

    return client

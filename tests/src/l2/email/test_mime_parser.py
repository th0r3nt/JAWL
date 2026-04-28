from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.l2_interfaces.email.utils import extract_text_from_email


def test_extract_text_from_simple_message():
    """Тест: Извлечение текста из простого сообщения."""
    msg = EmailMessage()
    msg.set_content("Just plain text.")

    res = extract_text_from_email(msg)
    assert res == "Just plain text."


def test_extract_text_from_multipart():
    """Тест: Извлечение текста из Multipart. Чистый текст имеет приоритет над HTML."""
    msg = MIMEMultipart("alternative")

    part1 = MIMEText("Plain text version.", "plain")
    part2 = MIMEText("<html><body>HTML version.</body></html>", "html")

    msg.attach(part1)
    msg.attach(part2)

    res = extract_text_from_email(msg)

    # Приоритет всегда у чистого текста, если он есть
    assert res == "Plain text version."


def test_extract_text_html_fallback():
    """Тест: Если чистого текста нет, парсер вытаскивает HTML и вырезает из него теги."""
    msg = MIMEMultipart("alternative")

    part = MIMEText("<html><body><p>Only HTML.</p></body></html>", "html")
    msg.attach(part)

    res = extract_text_from_email(msg)

    assert "Only HTML." in res
    assert "<p>" not in res

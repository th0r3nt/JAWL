"""
Утилиты для парсинга электронной почты.

Скрывают в себе боль работы с кодировками MIME, вложенными Multipart-сущностями
и HTML-мусором, возвращая агенту чистый и понятный текст.
"""

from email.header import decode_header
import email.message
import re

from src.utils._tools import clean_html


def decode_mime_header(header_value: str) -> str:
    """
    Нормально декодирует MIME-заголовки (например '=?UTF-8?B?...?=').

    Args:
        header_value: Сырая строка заголовка из IMAP.

    Returns:
        Человекочитаемая строка.
    """
    if not header_value:
        return "Unknown"

    decoded_parts = []
    for part, encoding in decode_header(header_value):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(encoding or "utf-8", errors="replace"))
            except LookupError:
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return "".join(decoded_parts)


def strip_html_tags(text: str) -> str:
    """Суровый и дешевый способ вырезать HTML-теги для экономии контекста."""
    clean = re.compile("<.*?>", re.DOTALL)
    return re.sub(clean, " ", text).strip()


def extract_text_from_email(msg: email.message.Message) -> str:
    """
    Вытаскивает чистый текст из лапши MIME-частей (Multipart писем).
    Отдает приоритет 'text/plain', но если есть только HTML — вырезает из него теги
    с помощью утилиты clean_html.

    Args:
        msg: Объект письма email.message.Message.

    Returns:
        Очищенный от HTML текст письма.
    """
    text_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if "attachment" in content_disposition:
                continue

            try:
                body = part.get_payload(decode=True)
                if body:
                    charset = part.get_content_charset() or "utf-8"
                    decoded_body = body.decode(charset, errors="replace")

                    if content_type == "text/plain":
                        text_parts.append(decoded_body)
                    elif content_type == "text/html":
                        html_parts.append(decoded_body)
            except Exception:
                pass
    else:
        try:
            body = msg.get_payload(decode=True)
            if body:
                charset = msg.get_content_charset() or "utf-8"
                decoded_body = body.decode(charset, errors="replace")
                if msg.get_content_type() == "text/plain":
                    text_parts.append(decoded_body)
                elif msg.get_content_type() == "text/html":
                    html_parts.append(decoded_body)
        except Exception:
            pass

    # Отдаем приоритет чистому тексту. Если его нет — берем HTML и чистим.
    if text_parts:
        return "\n".join(text_parts).strip()
    elif html_parts:
        raw_html = "\n".join(html_parts)
        return clean_html(raw_html)

    return "[Пустое сообщение или неподдерживаемый формат]"

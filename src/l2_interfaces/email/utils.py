from email.header import decode_header
import re

from src.utils._tools import clean_html


def decode_mime_header(header_value: str) -> str:
    """Нормально декодирует MIME-заголовки (=?UTF-8?B?...)."""
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
            decoded_parts.append(part)
    return "".join(decoded_parts)


def strip_html_tags(text: str) -> str:
    """Суровый и дешевый способ вырезать HTML-теги для экономии контекста."""
    clean = re.compile("<.*?>")
    return re.sub(clean, " ", text).strip()


def extract_text_from_email(msg) -> str:
    """Вытаскивает чистый текст из лапши MIME-частей."""
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

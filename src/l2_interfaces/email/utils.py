"""
Utilities for parsing email messages.

Hides the complexity of working with MIME encodings, nested Multipart entities,
and HTML junk, returning clean, understandable text to the agent.
"""

from email.header import decode_header
import email.message
import re

from src.utils._tools import clean_html
from src.utils.logger import main_logger


def decode_mime_header(header_value: str) -> str:
    """
    Correctly decodes MIME headers (e.g. '=?UTF-8?B?...?=').

    Args:
        header_value: Raw header string from IMAP.

    Returns:
        Human-readable string.
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
    """Rigorous and cheap way to strip HTML tags to save context."""
    clean = re.compile("<.*?>", re.DOTALL)
    return re.sub(clean, " ", text).strip()


def extract_text_from_email(msg: email.message.Message) -> str:
    """
    Extracts clean text from the nested MIME parts (Multipart emails).
    Prioritizes 'text/plain', but if only HTML is available, strips tags
    using the clean_html utility.

    Args:
        msg: email.message.Message email object.

    Returns:
        Cleaned text from the email.
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
            except Exception as e:
                main_logger.debug(
                    f"[Email MIME] Failed to decode MIME part ({part.get_content_type()}): {e}"
                )

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

    # Prioritize plain text. If not available - take HTML and clean it.
    if text_parts:
        return "\n".join(text_parts).strip()
    elif html_parts:
        raw_html = "\n".join(html_parts)
        return clean_html(raw_html)

    return "[Empty message or unsupported format]"

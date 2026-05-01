"""
Навыки агента для взаимодействия с электронной почтой.

Позволяют агенту читать инбокс, отправлять письма и безвозвратно удалять мусор.
Включают встроенную защиту от огромных писем-рассылок (обрезка через truncate_text).
"""

import asyncio
import email
from email.message import EmailMessage
from typing import Tuple

from src.utils.logger import system_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.email.client import EmailClient
from src.l2_interfaces.email.utils import decode_mime_header, extract_text_from_email
from src.l3_agent.skills.registry import SkillResult, skill


class EmailSkills:
    """Навыки для чтения, отправки и удаления писем."""

    def __init__(self, client: EmailClient) -> None:
        self.client = client

    @skill()
    async def read_email(self, uid: int) -> SkillResult:
        """
        Скачивает и читает полное содержимое письма по его уникальному идентификатору (UID).
        Автоматически конвертирует HTML-письма в чистый текст.

        Args:
            uid: Идентификатор письма (берется из списка 'Recent Inbox' на приборной панели).
        """

        def _read() -> Tuple[bool, str]:
            with self.client.imap_connection() as mail:
                status, msg_data = mail.uid("fetch", str(uid).encode(), "(RFC822)")
                if status != "OK" or not msg_data[0]:
                    return False, "Письмо не найдено."

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = decode_mime_header(msg.get("Subject", "Без темы"))
                sender = decode_mime_header(msg.get("From", "Неизвестен"))
                date = msg.get("Date", "Неизвестно")

                body = extract_text_from_email(msg)

                # Защита от гигантских рассылок и писем с вложениями
                body = truncate_text(body, 15000)

                report = f"От: {sender}\nДата: {date}\nТема: {subject}\n\n{body}"
                return True, report

        try:
            success, text = await asyncio.to_thread(_read)
            if success:
                system_logger.info(f"[Email] Прочитано письмо UID: {uid}")
                return SkillResult.ok(text)

            return SkillResult.fail(text)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении письма: {e}")

    @skill()
    async def send_email(self, to_email: str, subject: str, body: str) -> SkillResult:
        """
        Отправляет текстовое письмо на указанный электронный адрес.

        Args:
            to_email: Адрес получателя (например, 'user@gmail.com').
            subject: Тема письма.
            body: Основной текст письма.
        """

        def _send() -> None:
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = self.client.account
            msg["To"] = to_email

            with self.client.smtp_connection() as server:
                server.send_message(msg)

        try:
            await asyncio.to_thread(_send)
            return SkillResult.ok(f"Письмо успешно отправлено на {to_email}.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при отправке письма: {e}")

    @skill()
    async def delete_email(self, uid: int) -> SkillResult:
        """
        Безвозвратно удаляет письмо из почтового ящика по его UID.

        Args:
            uid: Идентификатор удаляемого письма.
        """

        def _delete() -> None:
            with self.client.imap_connection() as mail:
                # Ставим флаг "Удалено"
                mail.uid("STORE", str(uid).encode(), "+FLAGS", "(\\Deleted)")
                # Применяем удаление для всего ящика
                mail.expunge()

        try:
            await asyncio.to_thread(_delete)
            # Синхронизируем стейт
            await asyncio.to_thread(self.client.update_state_view)

            return SkillResult.ok("Письмо успешно удалено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении письма: {e}")

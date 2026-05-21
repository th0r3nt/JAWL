"""
Agent skills for interacting with email.

Allows the agent to read the inbox, send emails, and permanently delete trash.
Includes built-in protection against giant newsletter emails (truncation via truncate_text).
"""

import asyncio
import email
from email.message import EmailMessage
from typing import Tuple

from src.utils.logger import main_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.email.client import EmailClient
from src.l2_interfaces.email.utils import decode_mime_header, extract_text_from_email
from src.l3_agent.skills.registry import SkillResult, skill


class EmailSkills:
    """Skills for reading, sending, and deleting emails."""

    def __init__(self, client: EmailClient) -> None:
        self.client = client

    @skill()
    async def read_email(self, uid: int) -> SkillResult:
        """
        Downloads and reads full email content.
        """

        def _read() -> Tuple[bool, str]:
            with self.client.imap_connection() as mail:
                status, msg_data = mail.uid("fetch", str(uid).encode(), "(RFC822)")
                if status != "OK" or not msg_data[0]:
                    return False, "Email not found."

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = decode_mime_header(msg.get("Subject", "No subject"))
                sender = decode_mime_header(msg.get("From", "Unknown"))
                date = msg.get("Date", "Unknown")

                body = extract_text_from_email(msg)

                # Protection against giant newsletters and emails with attachments
                body = truncate_text(body, 15000)

                report = f"From: {sender}\nDate: {date}\nSubject: {subject}\n\n{body}"
                return True, report

        try:
            success, text = await asyncio.to_thread(_read)
            if success:
                main_logger.info(f"[Email] Read email UID: {uid}")
                return SkillResult.ok(text)

            return SkillResult.fail(text)

        except Exception as e:
            return SkillResult.fail(f"Error reading email: {e}")

    @skill()
    async def send_email(self, to_email: str, subject: str, body: str) -> SkillResult:
        """
        Sends a text email to the specified email address.
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
            return SkillResult.ok(f"Email successfully sent to {to_email}.")

        except Exception as e:
            return SkillResult.fail(f"Error sending email: {e}")

    @skill()
    async def delete_email(self, uid: int) -> SkillResult:
        """
        Deletes email from mailbox.
        """

        def _delete() -> None:
            with self.client.imap_connection() as mail:
                # Set the "Deleted" flag
                mail.uid("STORE", str(uid).encode(), "+FLAGS", "(\\Deleted)")
                # Apply deletion to the entire mailbox
                mail.expunge()

        try:
            await asyncio.to_thread(_delete)
            # Synchronize state
            await asyncio.to_thread(self.client.update_state_view)

            return SkillResult.ok("Email successfully deleted.")

        except Exception as e:
            return SkillResult.fail(f"Error deleting email: {e}")

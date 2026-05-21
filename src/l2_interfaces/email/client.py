"""
Stateful email client.

Manages IMAP/SMTP connections. Uses context managers to establish short-lived
sessions, protecting the system from socket timeouts during long idling.
Features strict text truncation to protect the agent from spam.
"""

import imaplib
import smtplib
import email
from contextlib import contextmanager
import asyncio
from typing import Iterator, Any

from src.utils.logger import main_logger
from src.l2_interfaces.email.state import EmailState
from src.l2_interfaces.email.utils import decode_mime_header


class EmailClient:
    """
    Mail server connection manager.
    Provides smart auto-selection of the provider (Gmail, Yandex, Mail.ru, etc.).
    """

    PROVIDERS = {
        "gmail.com": {"imap": "imap.gmail.com", "smtp": "smtp.gmail.com"},
        "yandex.ru": {"imap": "imap.yandex.ru", "smtp": "smtp.yandex.ru"},
        "mail.ru": {"imap": "imap.mail.ru", "smtp": "smtp.mail.ru"},
        "inbox.ru": {"imap": "imap.mail.ru", "smtp": "smtp.mail.ru"},
        "bk.ru": {"imap": "imap.mail.ru", "smtp": "smtp.mail.ru"},
        "outlook.com": {
            "imap": "outlook.office365.com",
            "smtp": "smtp-mail.outlook.com",
            "smtp_tls": True,
        },
        "hotmail.com": {
            "imap": "outlook.office365.com",
            "smtp": "smtp-mail.outlook.com",
            "smtp_tls": True,
        },
    }

    def __init__(self, state: EmailState, account: str, password: str) -> None:
        """
        Initializes the client.

        Args:
            state: L0 state (dashboard).
            account: Mail login (address).
            password: App Password (app password with 2FA).
        """

        self.state = state
        self.account = account.strip()
        self.password = password.strip()

        self.imap_server: str = ""
        self.smtp_server: str = ""
        self.smtp_tls: bool = False

    async def start(self) -> None:
        """
        Determines servers by email domain and performs a test connection.
        On success, marks the interface as Online.
        """

        domain = self.account.split("@")[-1].lower() if "@" in self.account else ""

        provider = self.PROVIDERS.get(domain)
        if not provider:
            main_logger.error(
                f"[Email] Unknown domain '{domain}'. Please use standard mail providers (Gmail, Yandex, Mail.ru)."
            )
            return

        self.imap_server = str(provider["imap"])
        self.smtp_server = str(provider["smtp"])
        self.smtp_tls = bool(provider.get("smtp_tls", False))

        try:
            # Test connection
            with self.imap_connection():
                pass

            self.state.is_online = True
            self.state.account_info = f"{self.account}"
            main_logger.info(f"[Email] Successful authorization in mailbox {self.account}")

            # Immediately update the dashboard
            await asyncio.to_thread(self.update_state_view)

        except Exception as e:
            self.state.account_info = "Authorization error (Incorrect App Password?)"
            main_logger.error(f"[Email] Authorization error for {self.account}: {e}")

    async def stop(self) -> None:
        """Stops the client (IMAP/SMTP sessions close automatically in context managers)."""
        self.state.is_online = False

    @contextmanager
    def imap_connection(self) -> Iterator[imaplib.IMAP4_SSL]:
        """
        Context manager for safe work with IMAP (open-do-close).

        Yields:
            Connected and authorized IMAP4_SSL instance.
        """

        mail = imaplib.IMAP4_SSL(self.imap_server)
        try:
            mail.login(self.account, self.password)
            mail.select("inbox")
            yield mail
        finally:
            try:
                mail.close()
            except Exception:
                pass
            mail.logout()

    @contextmanager
    def smtp_connection(self) -> Iterator[Any]:
        """
        Context manager for safe work with SMTP.

        Yields:
            Connected and authorized SMTP or SMTP_SSL instance.
        """

        port = 587 if self.smtp_tls else 465

        if self.smtp_tls:
            server = smtplib.SMTP(self.smtp_server, port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(self.smtp_server, port)

        try:
            server.login(self.account, self.password)
            yield server
        finally:
            server.quit()

    def update_state_view(self) -> None:
        """
        Lightweight method to update the mail dashboard.
        Downloads exclusively headers (Subject, From, Date) of the last N emails, ignoring bodies.
        Guarantees minimum traffic and agent token consumption.
        """

        if not self.state.is_online:
            return

        try:
            with self.imap_connection() as mail:
                # Search all emails (retrieve UIDs)
                status, messages = mail.uid("search", None, "ALL")
                if status != "OK":
                    return

                uids = messages[0].split()
                total_emails = len(uids)  # Total number of emails

                if not uids:
                    self.state.mailbox_preview = "Inbox is empty."
                    return

                recent_uids = uids[-self.state.recent_limit :]
                recent_uids.reverse()  # Newest on top

                lines = []
                for uid in recent_uids:
                    # Fetch headers only (very fast)
                    res, msg_data = mail.uid(
                        "fetch", uid, "(BODY[HEADER.FIELDS (SUBJECT FROM DATE)])"
                    )
                    if res == "OK" and msg_data[0]:
                        msg = email.message_from_bytes(msg_data[0][1])

                        subject = decode_mime_header(msg.get("Subject", "No subject"))
                        sender = decode_mime_header(msg.get("From", "Unknown"))
                        date = msg.get("Date", "Unknown")

                        lines.append(
                            f"- [UID: {uid.decode()}] From: {sender} | Subject: {subject} | {date}"
                        )

                # Assemble final text
                preview_text = "\n".join(lines)

                if total_emails > self.state.recent_limit:
                    hidden = total_emails - self.state.recent_limit
                    preview_text += f"\n\n...and {hidden} more emails hidden to save context."

                self.state.mailbox_preview = preview_text

        except Exception as e:
            main_logger.error(f"[Email] Error updating dashboard: {e}")

    async def get_context_block(self, **kwargs: Any) -> str:
        """Context provider for the agent's system prompt."""
        desc = "Description: Connecting to the specified mailbox account (IMAP/SMTP)."
        if not self.state.is_online:
            return f"### EMAIL [OFF] \n{desc}\nThe interface is disabled."

        return f"### EMAIL [ON] \n{desc}\nAccount: {self.state.account_info}\n\nRecent Inbox:\n{self.state.mailbox_preview}"

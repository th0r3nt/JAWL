"""
Stateful-клиент электронной почты (Email).

Управляет соединениями IMAP/SMTP. Использует Context Managers для кратковременного
поднятия сессий, защищая систему от таймаутов (socket drop) при длительном простое.
Имеет механизм жесткой обрезки (truncate) для защиты агента от спам-рассылок.
"""

import imaplib
import smtplib
import email
from contextlib import contextmanager
import asyncio
from typing import Iterator, Any

from src.utils.logger import system_logger
from src.l2_interfaces.email.state import EmailState
from src.l2_interfaces.email.utils import decode_mime_header


class EmailClient:
    """
    Менеджер соединений с почтовыми серверами.
    Обеспечивает умный автовыбор провайдера (Gmail, Yandex, Mail.ru и др.).
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
        Инициализирует клиент.

        Args:
            state: L0 стейт (приборная панель).
            account: Логин почты (адрес).
            password: App Password (пароль приложения с 2FA).
        """

        self.state = state
        self.account = account.strip()
        self.password = password.strip()

        self.imap_server: str = ""
        self.smtp_server: str = ""
        self.smtp_tls: bool = False

    async def start(self) -> None:
        """
        Определяет сервера по домену почты и выполняет тестовый коннект.
        В случае успеха помечает интерфейс как Online.
        """

        domain = self.account.split("@")[-1].lower() if "@" in self.account else ""

        provider = self.PROVIDERS.get(domain)
        if not provider:
            system_logger.error(
                f"[Email] Неизвестный домен '{domain}'. Пожалуйста, используйте стандартные почтовики (Gmail, Yandex, Mail.ru)."
            )
            return

        self.imap_server = str(provider["imap"])
        self.smtp_server = str(provider["smtp"])
        self.smtp_tls = bool(provider.get("smtp_tls", False))

        try:
            # Тестовый коннект
            with self.imap_connection():
                pass

            self.state.is_online = True
            self.state.account_info = f"{self.account} (IMAP/SMTP настроены автоматически)"
            system_logger.info(f"[Email] Успешная авторизация в ящике {self.account}")

            # Сразу обновляем дашборд
            await asyncio.to_thread(self.update_state_view)

        except Exception as e:
            self.state.account_info = "Ошибка авторизации (Неверный пароль приложения?)"
            system_logger.error(f"[Email] Ошибка авторизации {self.account}: {e}")

    async def stop(self) -> None:
        """Останавливает клиент (сессии IMAP/SMTP закрываются сами в context managers)."""
        self.state.is_online = False

    @contextmanager
    def imap_connection(self) -> Iterator[imaplib.IMAP4_SSL]:
        """
        Контекстный менеджер для безопасной работы с IMAP (открыл-сделал-закрыл).

        Yields:
            Подключенный и авторизованный инстанс IMAP4_SSL.
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
        Контекстный менеджер для безопасной работы с SMTP.

        Yields:
            Подключенный и авторизованный инстанс SMTP или SMTP_SSL.
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
        Легковесный метод обновления дашборда почты.
        Скачивает исключительно заголовки (Subject, From, Date) последних N писем, игнорируя тела.
        Гарантирует минимальный расход трафика и токенов агента.
        """

        if not self.state.is_online:
            return

        try:
            with self.imap_connection() as mail:
                # Ищем все письма (получаем UIDs)
                status, messages = mail.uid("search", None, "ALL")
                if status != "OK":
                    return

                uids = messages[0].split()
                total_emails = len(uids)  # Считаем общее количество писем

                if not uids:
                    self.state.mailbox_preview = "Ящик пуст."
                    return

                recent_uids = uids[-self.state.recent_limit :]
                recent_uids.reverse()  # Свежие сверху

                lines = []
                for uid in recent_uids:
                    # Запрашиваем только заголовки (очень быстро)
                    res, msg_data = mail.uid(
                        "fetch", uid, "(BODY[HEADER.FIELDS (SUBJECT FROM DATE)])"
                    )
                    if res == "OK" and msg_data[0]:
                        msg = email.message_from_bytes(msg_data[0][1])

                        subject = decode_mime_header(msg.get("Subject", "Без темы"))
                        sender = decode_mime_header(msg.get("From", "Неизвестен"))
                        date = msg.get("Date", "Неизвестно")

                        lines.append(
                            f"- [UID: {uid.decode()}] От: {sender} | Тема: {subject} | {date}"
                        )

                # Собираем итоговый текст
                preview_text = "\n".join(lines)

                if total_emails > self.state.recent_limit:
                    hidden = total_emails - self.state.recent_limit
                    preview_text += (
                        f"\n\n...и еще {hidden} писем скрыто для экономии контекста."
                    )

                self.state.mailbox_preview = preview_text

        except Exception as e:
            system_logger.error(f"[Email] Ошибка обновления дашборда: {e}")

    async def get_context_block(self, **kwargs: Any) -> str:
        """Формирует Markdown-блок для приборной панели агента."""

        if not self.state.is_online:
            return "### EMAIL [OFF] \nИнтерфейс отключен."

        return f"### EMAIL [ON] \nAccount: {self.state.account_info}\n\nRecent Inbox:\n{self.state.mailbox_preview}"

import imaplib
import smtplib
import email
from contextlib import contextmanager
import asyncio

from src.utils.logger import system_logger
from src.l0_state.interfaces.state import EmailState
from src.l2_interfaces.email.utils import decode_mime_header


class EmailClient:
    """
    Stateful-клиент для работы с почтой.
    Умный автовыбор серверов. Не держит постоянных соединений во избежание таймаутов.
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

    def __init__(self, state: EmailState, account: str, password: str):
        self.state = state
        self.account = account.strip()
        self.password = password.strip()

        self.imap_server = None
        self.smtp_server = None
        self.smtp_tls = False

    async def start(self) -> None:
        """
        Определяет сервера и проверяет авторизацию.
        """

        domain = self.account.split("@")[-1].lower() if "@" in self.account else ""

        provider = self.PROVIDERS.get(domain)
        if not provider:
            system_logger.error(
                f"[Email] Неизвестный домен '{domain}'. Пожалуйста, используйте стандартные почтовики (Gmail, Yandex, Mail.ru)."
            )
            return

        self.imap_server = provider["imap"]
        self.smtp_server = provider["smtp"]
        self.smtp_tls = provider.get("smtp_tls", False)

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
        self.state.is_online = False

    @contextmanager
    def imap_connection(self):
        """
        Контекстный менеджер для безопасной работы с IMAP (открыл-сделал-закрыл).
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
    def smtp_connection(self):
        """
        Контекстный менеджер для безопасной работы с SMTP.
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
        Быстро подтягивает последние заголовки для L0 State (без загрузки тел писем).
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
                    preview_text += f"\n\n...и еще {hidden} писем скрыто для экономии контекста."
                
                self.state.mailbox_preview = preview_text

        except Exception as e:
            system_logger.error(f"[Email] Ошибка обновления дашборда: {e}")

    async def get_context_block(self, **kwargs) -> str:
        if not self.state.is_online:
            return "### EMAIL [OFF] \nИнтерфейс отключен."

        return f"### EMAIL [ON] \nAccount: {self.state.account_info}\n\nRecent Inbox:\n{self.state.mailbox_preview}"

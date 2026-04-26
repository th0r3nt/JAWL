import asyncio
import email
from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.state import EmailState
from src.l2_interfaces.email.client import EmailClient
from src.l2_interfaces.email.utils import decode_mime_header


class EmailEvents:
    """Фоновый мониторинг новых писем."""

    def __init__(
        self, client: EmailClient, state: EmailState, event_bus: EventBus, interval_sec: int
    ):
        self.client = client
        self.state = state
        self.bus = event_bus
        self.interval = interval_sec
        self._is_running = False
        self._polling_task = None

        self._seen_uids = set()

    async def start(self) -> None:
        if not self.client.state.is_online or self._is_running:
            return

        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        system_logger.info("[Email] Фоновый поллинг новых писем запущен.")

    async def stop(self) -> None:
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

    def _check_new_emails(self):
        try:
            with self.client.imap_connection() as mail:
                # Ищем непрочитанные
                status, messages = mail.uid("search", None, "UNSEEN")
                if status != "OK" or not messages[0]:
                    return []

                new_uids = messages[0].split()
                events_to_emit = []

                for uid in new_uids:
                    uid_str = uid.decode()
                    if uid_str in self._seen_uids:
                        continue

                    self._seen_uids.add(uid_str)

                    # Читаем заголовки для ивента
                    res, msg_data = mail.uid(
                        "fetch", uid, "(BODY[HEADER.FIELDS (SUBJECT FROM)])"
                    )
                    if res == "OK" and msg_data[0]:
                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = decode_mime_header(msg.get("Subject", "Без темы"))
                        sender = decode_mime_header(msg.get("From", "Неизвестен"))

                        events_to_emit.append(
                            {"uid": uid_str, "subject": subject, "sender": sender}
                        )
                return events_to_emit
        except Exception as e:
            system_logger.error(f"[Email] Ошибка при проверке почты: {e}")
            return []

    async def _loop(self):
        while self._is_running:
            try:
                new_emails = await asyncio.to_thread(self._check_new_emails)

                if new_emails:
                    # Дергаем обновление дашборда
                    await asyncio.to_thread(self.client.update_state_view)

                    # Кидаем агенту ивенты
                    for mail_evt in new_emails:
                        await self.bus.publish(
                            Events.EMAIL_INCOMING,
                            uid=mail_evt["uid"],
                            sender_name=mail_evt["sender"],
                            message=f"Новое письмо. Тема: {mail_evt['subject']}",
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Email] Ошибка в цикле мониторинга почты: {e}")

            await asyncio.sleep(self.interval)

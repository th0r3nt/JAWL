"""
Background email poller (IMAP).

Regularly polls the server for new unread emails.
Generates an 'EMAIL_INCOMING' event in the EventBus to wake up the agent.
"""

import asyncio
import email
from collections import OrderedDict
from typing import List, Dict, Optional

from src.utils.logger import main_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l2_interfaces.email.state import EmailState
from src.l2_interfaces.email.client import EmailClient
from src.l2_interfaces.email.utils import decode_mime_header


class EmailEvents:
    """Background monitoring of new emails."""

    def __init__(
        self, client: EmailClient, state: EmailState, event_bus: EventBus, interval_sec: int
    ) -> None:
        """
        Initializes the mail poller.

        Args:
            client: EmailClient instance.
            state: Interface state object.
            event_bus: Global event bus.
            interval_sec: Interval between requests to IMAP.
        """
        self.client = client
        self.state = state
        self.bus = event_bus
        self.interval = interval_sec
        self._is_running = False
        self._polling_task: Optional[asyncio.Task] = None

        # LRU cache of already processed email UIDs.
        # Hard bounded: otherwise it would grow infinitely for users who
        # accumulate UNSEEN emails without reading them.
        # OrderedDict + move_to_end provides O(1) on seen-check, insert, and evict.
        self._seen_uids_capacity: int = 10_000
        self._seen_uids: "OrderedDict[str, None]" = OrderedDict()

    async def start(self) -> None:
        """Starts background polling cycle."""
        if not self.client.state.is_online or self._is_running:
            return

        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        main_logger.info("[Email] Background unread mail polling started.")

    async def stop(self) -> None:
        """Stops the cycle."""
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        main_logger.info("[Email] Background unread mail polling stopped.")

    def _check_new_emails(self) -> List[Dict[str, str]]:
        """
        Connects to IMAP and searches for messages with the UNSEEN flag.

        Returns:
            List of dicts with metadata about new emails.
        """
        try:
            with self.client.imap_connection() as mail:
                # Search for unread
                status, messages = mail.uid("search", None, "UNSEEN")
                if status != "OK" or not messages[0]:
                    return []

                new_uids = messages[0].split()
                events_to_emit = []

                for uid in new_uids:
                    uid_str = uid.decode()
                    if uid_str in self._seen_uids:
                        # Refresh LRU position to not evict active UID.
                        self._seen_uids.move_to_end(uid_str)
                        continue

                    self._seen_uids[uid_str] = None
                    if len(self._seen_uids) > self._seen_uids_capacity:
                        # Evict the oldest UID (FIFO edge of LRU).
                        self._seen_uids.popitem(last=False)

                    # Read headers for the event
                    res, msg_data = mail.uid(
                        "fetch", uid, "(BODY[HEADER.FIELDS (SUBJECT FROM)])"
                    )
                    if res == "OK" and msg_data[0]:
                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = decode_mime_header(msg.get("Subject", "No subject"))
                        sender = decode_mime_header(msg.get("From", "Unknown"))

                        events_to_emit.append(
                            {"uid": uid_str, "subject": subject, "sender": sender}
                        )
                return events_to_emit
        except Exception as e:
            main_logger.error(f"[Email] Error checking mail: {e}")
            return []

    async def _loop(self) -> None:
        """Main mail polling loop."""
        while self._is_running:
            try:
                new_emails = await asyncio.to_thread(self._check_new_emails)

                if new_emails:
                    # Trigger dashboard update
                    await asyncio.to_thread(self.client.update_state_view)

                    # Publish events to the agent
                    for mail_evt in new_emails:
                        await self.bus.publish(
                            Events.EMAIL_INCOMING,
                            uid=mail_evt["uid"],
                            sender_name=mail_evt["sender"],
                            message=f"New email. Subject: {mail_evt['subject']}",
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                main_logger.error(f"[Email] Error in mail monitoring loop: {e}")

            await asyncio.sleep(self.interval)

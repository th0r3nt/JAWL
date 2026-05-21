"""
Background poller for RSS feeds.
"""

import asyncio

from src.utils.logger import main_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils._tools import clean_html

from src.l2_interfaces.web.rss.state import WebRSSState
from src.l2_interfaces.web.rss.client import WebRSSClient


class WebRSSEvents:
    """Background poller for RSS feeds."""

    def __init__(self, client: WebRSSClient, state: WebRSSState, event_bus: EventBus):
        self.client = client
        self.state = state
        self.bus = event_bus

        self._is_running = False
        self._polling_task = None

        # Cache of viewed entries (URL or ID) to avoid firing duplicate events
        self._seen_entries = set()

    async def start(self) -> None:
        if self._is_running or not self.client.config.feeds:
            return

        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        main_logger.info(
            f"[Web RSS] Background RSS feed polling started (Interval: {self.client.config.polling_interval_sec}s)."
        )

    async def stop(self) -> None:
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

    async def _loop(self):
        # On the first run, simply gather current IDs to avoid spamming the history
        await self._poll_feeds(is_first_run=True)

        while self._is_running:
            try:
                await asyncio.sleep(self.client.config.polling_interval_sec)
                await self._poll_feeds(is_first_run=False)
            except asyncio.CancelledError:
                break
            except Exception as e:
                main_logger.error(f"[Web RSS] Error in RSS monitoring loop: {e}")

    async def _poll_feeds(self, is_first_run: bool):
        all_latest_entries = []

        for feed_cfg in self.client.config.feeds:
            try:
                feed = await self.client.fetch_feed(feed_cfg.url)

                if not feed.entries:
                    continue

                for entry in feed.entries[: self.client.config.recent_limit]:
                    entry_id = entry.get("id") or entry.get("link")

                    if not entry_id:
                        continue

                    # Add to the dashboard list (L0 State)
                    title = clean_html(entry.get("title", "Untitled"))
                    link = entry.get("link", "")
                    all_latest_entries.append(f"- [{feed_cfg.name}] {title}\n  URL: {link}")

                    # If this is a new entry and not the first run - publish the event
                    if entry_id not in self._seen_entries:
                        self._seen_entries.add(entry_id)

                        if not is_first_run:
                            await self.bus.publish(
                                Events.RSS_NEW_ENTRY,
                                feed_name=feed_cfg.name,
                                title=title,
                                link=link,
                                message=f"New publication in '{feed_cfg.name}': {title}",
                            )

                # Limit the set size to prevent memory leaks
                limit = 1000
                if len(self._seen_entries) > limit:
                    self._seen_entries = set(list(self._seen_entries)[-limit:])

            except Exception as e:
                main_logger.debug(f"[Web RSS] Error polling feed {feed_cfg.name}: {e}")

        # Update the dashboard
        if all_latest_entries:
            # Show only the last N of all gathered
            display = all_latest_entries[: self.client.config.recent_limit]
            self.state.latest_news = "\n".join(display)

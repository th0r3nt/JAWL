"""
L2 client for RSS/Atom feed parsing.

Manages feed status, configurations, and fetches remote feeds.
"""

import asyncio
import feedparser
from typing import Any

from src.l2_interfaces.web.rss.state import WebRSSState
from src.utils.settings import WebRSSConfig


class WebRSSClient:
    """Client for RSS/Atom feed parsing."""

    def __init__(self, state: WebRSSState, config: WebRSSConfig):
        self.state = state
        self.config = config

        self.state.is_online = True
        self._update_feeds_status()

    def _update_feeds_status(self):
        if not self.config.feeds:
            self.state.feeds_status = "No RSS feeds configured."
            return

        feed_lines = [f"- {f.name} ({f.url})" for f in self.config.feeds]
        self.state.feeds_status = f"Tracked feeds ({len(feed_lines)}):\n" + "\n".join(
            feed_lines
        )

    async def fetch_feed(self, url: str) -> dict:
        """
        Asynchronous wrapper for feedparser.
        """

        def _fetch():
            # feedparser handles HTTP requests, redirects, and ETag on its own
            return feedparser.parse(url)

        return await asyncio.to_thread(_fetch)

    async def get_context_block(self, **kwargs: Any) -> str:
        """Context block for system prompt context."""
        desc = "Description: RSS/Atom feed parsing and tracking."
        if not self.state.is_online:
            return f"### WEB RSS [OFF]\n{desc}\nThe interface is disabled."

        return (
            f"### WEB RSS [ON]\n"
            f"{desc}\n"
            f"* Status: {self.state.feeds_status}\n\n"
            f"* Recent News:\n{self.state.latest_news}"
        )

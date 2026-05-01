import asyncio
import feedparser

from src.l0_state.interfaces.web.rss_state import WebRSSState
from src.utils.settings import WebRSSConfig


class WebRSSClient:
    """
    Клиент для парсинга RSS/Atom лент.
    """

    def __init__(self, state: WebRSSState, config: WebRSSConfig):
        self.state = state
        self.config = config

        self.state.is_online = True
        self._update_feeds_status()

    def _update_feeds_status(self):
        if not self.config.feeds:
            self.state.feeds_status = "Нет настроенных RSS-лент."
            return

        feed_lines = [f"- {f.name} ({f.url})" for f in self.config.feeds]
        self.state.feeds_status = f"Отслеживаемые ленты ({len(feed_lines)}):\n" + "\n".join(
            feed_lines
        )

    async def fetch_feed(self, url: str) -> dict:
        """
        Асинхронная обертка для feedparser.
        """

        def _fetch():
            # feedparser сам отлично справляется с HTTP-запросами, редиректами и ETag
            return feedparser.parse(url)

        return await asyncio.to_thread(_fetch)

    async def get_context_block(self, **kwargs) -> str:
        if not self.state.is_online:
            return "### WEB RSS [OFF]\nИнтерфейс отключен."

        return (
            f"### WEB RSS [ON]\n"
            f"* Статус: {self.state.feeds_status}\n\n"
            f"* Последние новости:\n{self.state.latest_news}"
        )

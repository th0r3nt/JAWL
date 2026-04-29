import asyncio

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils._tools import clean_html

from src.l0_state.interfaces.state import WebRSSState
from src.l2_interfaces.web.rss.client import WebRSSClient


class WebRSSEvents:
    """
    Фоновый поллер для RSS-лент.
    """

    def __init__(self, client: WebRSSClient, state: WebRSSState, event_bus: EventBus):
        self.client = client
        self.state = state
        self.bus = event_bus

        self._is_running = False
        self._polling_task = None

        # Кэш просмотренных записей (URL или ID), чтобы не кидать одни и те же ивенты
        self._seen_entries = set()

    async def start(self) -> None:
        if self._is_running or not self.client.config.feeds:
            return

        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        system_logger.info(
            f"[Web RSS] Фоновый поллинг RSS-лент запущен (Интервал: {self.client.config.polling_interval_sec}с)."
        )

    async def stop(self) -> None:
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

    async def _loop(self):
        # При первом запуске просто собираем текущие ID, чтобы не спамить историей
        await self._poll_feeds(is_first_run=True)

        while self._is_running:
            try:
                await asyncio.sleep(self.client.config.polling_interval_sec)
                await self._poll_feeds(is_first_run=False)
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Web RSS] Ошибка в цикле мониторинга RSS: {e}")

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

                    # Добавляем в список для приборной панели (L0 State)
                    title = clean_html(entry.get("title", "Без заголовка"))
                    link = entry.get("link", "")
                    all_latest_entries.append(f"- [{feed_cfg.name}] {title}\n  URL: {link}")

                    # Если это новая запись и не первый запуск - публикуем ивент
                    if entry_id not in self._seen_entries:
                        self._seen_entries.add(entry_id)

                        if not is_first_run:
                            await self.bus.publish(
                                Events.RSS_NEW_ENTRY,
                                feed_name=feed_cfg.name,
                                title=title,
                                link=link,
                                message=f"Новая публикация в '{feed_cfg.name}': {title}",
                            )

                # Ограничиваем размер сета, чтобы не было утечек памяти
                limit = 1000  # TODO: перенести в yaml
                if len(self._seen_entries) > limit:
                    self._seen_entries = set(list(self._seen_entries)[-limit:])

            except Exception as e:
                system_logger.debug(f"[Web RSS] Ошибка поллинга ленты {feed_cfg.name}: {e}")

        # Обновляем приборную панель
        if all_latest_entries:
            # Показываем только последние N из всех собранных
            display = all_latest_entries[: self.client.config.recent_limit]
            self.state.latest_news = "\n".join(display)

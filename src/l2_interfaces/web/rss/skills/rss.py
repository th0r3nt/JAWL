"""
Навыки для чтения Atom/RSS новостных лент.
Позволяют агенту извлекать чистый контент (Summary/Description) без перехода на оригинальные сайты.
"""

from src.utils.logger import system_logger
from src.utils._tools import truncate_text, clean_html
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.rss.client import WebRSSClient


class WebRSSSkills:
    """Навыки для чтения RSS/Atom лент."""

    def __init__(self, client: WebRSSClient):
        self.client = client

    @skill()
    async def list_feeds(self) -> SkillResult:
        """
        Возвращает список сохраненных (отслеживаемых) RSS-лент.
        """
        if not self.client.config.feeds:
            return SkillResult.ok("Список сохраненных RSS-лент пуст.")

        lines = ["Доступные RSS-ленты:"]
        for feed in self.client.config.feeds:
            lines.append(f"- Имя: '{feed.name}' | URL: {feed.url}")

        return SkillResult.ok("\n".join(lines))

    @skill()
    async def read_feed(self, url: str, limit: int = 5) -> SkillResult:
        """
        Скачивает XML-ленту, парсит записи и вырезает HTML-мусор из описаний.

        Args:
            url: Прямая ссылка на RSS/Atom файл.
            limit: Максимальное количество последних постов для чтения.
        """

        try:
            feed = await self.client.fetch_feed(url)

            if feed.bozo:
                system_logger.warning(
                    f"[Web] Лента {url} имеет ошибки формата, но будет распарсена частично."
                )

            if not feed.entries:
                return SkillResult.ok(
                    f"Лента по адресу '{url}' пуста, недоступна или не содержит записей."
                )

            limit = max(1, min(limit, 20))  # Защита от переполнения контекста
            lines = [f"Последние публикации из '{url}':"]

            for entry in feed.entries[:limit]:
                title = clean_html(entry.get("title", "Без заголовка"))
                link = entry.get("link", "Нет ссылки")
                date = entry.get("published", entry.get("updated", "Неизвестная дата"))

                # Извлекаем саммари и чистим мощным парсером
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                summary = truncate_text(summary, max_chars=400, suffix="...")

                lines.append(
                    f"### {title}\n* Дата: {date}\n* URL: {link}\n* Summary: {summary}\n"
                )

            system_logger.info(
                f"[Web] Прочитана лента '{url}' ({len(feed.entries[:limit])} записей)."
            )
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении ленты '{url}': {e}")

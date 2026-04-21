import asyncio
import trafilatura

from src.utils.logger import system_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.web.search.client import WebSearchClient

from src.l3_agent.skills.registry import skill, SkillResult


class WebPages:
    """Навыки чтения и извлечения текста из веб-страниц."""

    def __init__(self, client: WebSearchClient):
        self.client = client

    async def read_raw(self, url: str) -> str | None:
        """Сырое чтение страницы."""

        def _fetch():
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            return trafilatura.extract(
                downloaded,
                include_links=True,
                include_images=False,
                include_formatting=True,
            )

        return await asyncio.to_thread(_fetch)

    @skill()
    async def read_webpage(self, url: str) -> SkillResult:
        """Читает текстовое содержимое веб-страницы по URL."""

        try:
            text = await self.read_raw(url)

            if not text:
                return SkillResult.fail(
                    f"Ошибка: не удалось прочитать {url} (капча или нет текста)."
                )

            total_len = len(text)

            if total_len > self.client.max_page_chars:
                text = truncate_text(text, self.client.max_page_chars, "... [Текст обрезан]")
                system_logger.info(f"[Web] Прочитана страница (с обрезкой): {url}")
            else:
                system_logger.info(f"[Web] Прочитана страница (полностью): {url}")

            header = f"[Веб-страница | Прочитано: {len(text)}/{total_len} симв.]\n{'='*40}\n"

            self.client.state.add_history(f"Чтение страницы: {url}")
            return SkillResult.ok(header + text)

        except Exception as e:
            return SkillResult.fail(f"Ошибка парсинга страницы: {e}")

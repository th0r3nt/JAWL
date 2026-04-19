import asyncio
import trafilatura

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.search.client import WebClient


class WebPages:
    """Навыки чтения и извлечения текста из веб-страниц."""

    def __init__(self, client: WebClient):
        self.client = client

    async def read_raw(self, url: str) -> str | None:
        """Сырое чтение страницы. Вынесен отдельно для research.py."""

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

            # Защита контекста от "тяжелых" страниц
            if len(text) > self.client.max_page_chars:
                text = text[: self.client.max_page_chars] + "\n\n... [Текст обрезан]"

            system_logger.info(f"[Web] Прочитана страница: {url}")
            self.client.state.add_history(f"Чтение страницы: {url}")
            return SkillResult.ok(text)

        except Exception as e:
            return SkillResult.fail(f"Ошибка парсинга страницы: {e}")

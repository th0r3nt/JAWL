import asyncio
from typing import Any
from ddgs import DDGS # Важно: Импорт ddgs - единственно верный, иначе поиск к чертям сломается

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.search.client import WebSearchClient


class DuckDuckGoSearch:
    def __init__(self, client: WebSearchClient):
        self.client = client
        # Глобальный ограничитель: Cloudflare (DDG) банит за мощные параллельные запросы.
        # Семафор гарантирует, что даже при DeepResearch мы не делаем больше 2-х запросов одновременно.
        self._semaphore = asyncio.Semaphore(2)

    async def search_raw(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        def _do_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        last_err = None

        async with self._semaphore:
            # Делаем 3 попытки с экспоненциальной паузой
            for attempt in range(3):
                try:
                    return await asyncio.to_thread(_do_search)
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(1 * (2**attempt))

        system_logger.error(f"[Web] DDG Rate Limit исчерпан для запроса '{query}': {last_err}")
        raise last_err

    @skill()
    async def search(self, query: str, max_results: int = 5) -> SkillResult:
        """
        Ищет информацию в интернете. Возвращает список ссылок и кратких сниппетов.
        """

        try:
            results = await self.search_raw(query, max_results)
            if not results:
                return SkillResult.ok(f"По запросу '{query}' ничего не найдено.")

            formatted = [
                f"Title: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}"
                for r in results
            ]
            system_logger.info(f"[Web] Выполнен поиск (DDG) по запросу: '{query}'")
            self.client.state.add_history(f"Поиск DDG: '{query}'")

            return SkillResult.ok("\n\n".join(formatted))

        except Exception as e:
            return SkillResult.fail(f"Ошибка веб-поиска (DDG): {e}")

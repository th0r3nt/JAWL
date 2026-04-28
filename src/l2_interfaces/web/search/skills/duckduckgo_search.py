import asyncio
import time
from duckduckgo_search import DDGS
from typing import Any

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.search.client import WebSearchClient


class DuckDuckGoSearch:
    def __init__(self, client: WebSearchClient):
        self.client = client

    async def search_raw(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        def _do_search():
            last_err = None
            # DDG часто кидает 202 RateLimit. Делаем 3 попытки с увеличивающейся паузой.
            for attempt in range(3):
                try:
                    with DDGS() as ddgs:
                        return list(ddgs.text(query, max_results=max_results))
                except Exception as e:
                    last_err = e
                    time.sleep(1 * (attempt + 1))
            
            # Если 3 раза упало - значит IP реально улетел в шэдоу-бан на некоторое время
            raise last_err

        return await asyncio.to_thread(_do_search)

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

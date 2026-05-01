"""
Поисковый движок Tavily (Стратегия).
Платный (с free тиром), сверхбыстрый и оптимизированный специально для ИИ-агентов.
"""

import json
import asyncio
import urllib.request
import urllib.error
from typing import Any, List, Dict

from src.utils.logger import system_logger
from src.l2_interfaces.web.search.client import WebSearchClient
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents


class TavilySearch:
    """Движок поиска ссылок через Tavily API."""

    def __init__(self, client: WebSearchClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    async def search_raw(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Внутренний метод для сырого поиска (используется DeepResearch)."""

        def _do_search() -> List[Dict[str, Any]]:
            url = "https://api.tavily.com/search"
            payload = json.dumps(
                {
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                }
            ).encode("utf-8")

            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")

            with urllib.request.urlopen(req, timeout=self.client.timeout) as response:
                res = json.loads(response.read().decode("utf-8"))

            # Маппинг под формат DDG для совместимости в DeepResearch
            formatted = []
            for item in res.get("results", []):
                formatted.append(
                    {
                        "title": item.get("title", "Unknown"),
                        "href": item.get("url", ""),
                        "body": item.get("content", ""),
                    }
                )
            return formatted

        return await asyncio.to_thread(_do_search)

    @skill(swarm_roles=[Subagents.WEB_RESEARCHER])
    async def search(self, query: str, max_results: int = 5) -> SkillResult:
        """
        Ищет информацию в интернете (Tavily AI Search).
        Возвращает список ссылок и кратких текстовых сниппетов.

        Args:
            query: Текст запроса.
            max_results: Лимит возвращаемых ссылок.
        """
        try:
            results = await self.search_raw(query, max_results)
            if not results:
                return SkillResult.ok(f"По запросу '{query}' ничего не найдено.")

            formatted = [
                f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}" for r in results
            ]
            system_logger.info(f"[Web] Выполнен поиск (Tavily) по запросу: '{query}'")
            self.client.state.add_history(f"Поиск Tavily: '{query}'")
            return SkillResult.ok("\n\n".join(formatted))

        except Exception as e:
            return SkillResult.fail(f"Ошибка веб-поиска (Tavily): {e}")

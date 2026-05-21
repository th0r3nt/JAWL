"""
Tavily search engine (Strategy).

Paid (with free tier), ultra-fast and optimized specifically for AI agents.
"""

import json
import asyncio
import urllib.request
import urllib.error
from typing import Any, List, Dict

from src.utils.logger import main_logger
from src.l2_interfaces.web.search.client import WebSearchClient
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents


class TavilySearch:
    """Link search engine via Tavily API."""

    def __init__(self, client: WebSearchClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    async def search_raw(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Internal method for raw search (used by DeepResearch)."""

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

            # Mapping to DDG format for compatibility in DeepResearch
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

    @skill(swarm=[Subagents.WEB_RESEARCHER])
    async def search(self, query: str, max_results: int = 5) -> SkillResult:
        """
        Searches web via Tavily AI.
        Returns links and short snippets.
        """
        try:
            results = await self.search_raw(query, max_results)
            if not results:
                return SkillResult.ok(f"Nothing found for query '{query}'.")

            formatted = [
                f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}" for r in results
            ]
            main_logger.info(f"[Web] Search (Tavily) completed for query: '{query}'")
            self.client.state.add_history(f"Tavily Search: '{query}'")
            return SkillResult.ok("\n\n".join(formatted))

        except Exception as e:
            return SkillResult.fail(f"Web search error (Tavily): {e}")

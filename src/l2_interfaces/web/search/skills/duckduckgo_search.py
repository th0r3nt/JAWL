"""
DuckDuckGo search engine (Strategy).

Free, but subject to rate limits from Cloudflare.
Equipped with a semaphore to limit parallel threads and retries (Exponential Backoff).
"""

import asyncio
from typing import Any, List, Dict
from ddgs import DDGS  # Unique import name is required for correct execution

from src.utils.logger import main_logger
from src.l2_interfaces.web.search.client import WebSearchClient
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

# Number of attempts and base Exponential Backoff delay.
# Pauses between attempts: 1s, 2s (before the last attempt).
DDG_MAX_ATTEMPTS = 3
DDG_BACKOFF_BASE_SEC = 1.0


class DuckDuckGoSearch:
    """Link search engine via DuckDuckGo."""

    def __init__(self, client: WebSearchClient) -> None:
        self.client = client
        # Global limiter: Cloudflare (DDG) bans for intensive parallel requests.
        # Semaphore ensures that even during DeepResearch, we make no more than 2 parallel requests.
        self._semaphore = asyncio.Semaphore(2)

    async def search_raw(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Internal method for raw search (used by DeepResearch).
        """

        def _do_search() -> List[Dict[str, Any]]:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        last_err: Exception | None = None

        async with self._semaphore:
            for attempt in range(DDG_MAX_ATTEMPTS):
                try:
                    return await asyncio.to_thread(_do_search)
                except Exception as e:
                    last_err = e
                    # Do not sleep after the last attempt, exit immediately.
                    if attempt == DDG_MAX_ATTEMPTS - 1:
                        break
                    await asyncio.sleep(DDG_BACKOFF_BASE_SEC * (2**attempt))

        main_logger.error(f"[Web] DDG Rate Limit exhausted for query '{query}': {last_err}")
        assert last_err is not None  # logically unreachable, but keeps typecheckers happy
        raise last_err

    @skill(swarm=[Subagents.WEB_RESEARCHER])
    async def search(self, query: str, max_results: int = 5) -> SkillResult:
        """
        Searches the web via DuckDuckGo. Returns links and short snippets.
        """
        try:
            results = await self.search_raw(query, max_results)
            if not results:
                return SkillResult.ok(f"Nothing found for query '{query}'.")

            formatted = [
                f"Title: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}"
                for r in results
            ]
            main_logger.info(f"[Web] Search (DDG) completed for query: '{query}'")
            self.client.state.add_history(f"DDG Search: '{query}'")

            return SkillResult.ok("\n\n".join(formatted))

        except Exception as e:
            return SkillResult.fail(f"Web search error (DDG): {e}")

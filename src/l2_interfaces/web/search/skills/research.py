"""
Asynchronous OSINT investigation module (Deep Research).

Orchestrates parallel execution of search engines (Tavily/DDG)
and text parsers (Jina/Trafilatura) for massive fact-gathering.
"""

import asyncio
from typing import List, Any

from src.utils.logger import main_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.web.search.client import WebSearchClient

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents


class DeepResearch:
    """Skills for deep parallel web research."""

    def __init__(self, client: WebSearchClient, searcher: Any, reader: Any) -> None:
        self.client = client
        self.searcher = searcher
        self.reader = reader

    @skill(swarm=[Subagents.WEB_RESEARCHER])
    async def deep_research(self, queries: List[str]) -> SkillResult:
        """
        Mass parallel fact-gathering.
        Takes search queries, googles concurrently, extracts unique links, reads pages, returns report.
        """

        if not queries:
            return SkillResult.fail("Error: Query list is empty.")

        queries = [str(q) for q in queries]

        # Get settings from client
        cfg = self.client.deep_research_config

        if len(queries) > cfg.max_queries:
            # Limit the number of parallel queries for API stability
            queries = queries[: cfg.max_queries]

        try:
            main_logger.info(f"[Web] Starting deep_research for {len(queries)} queries.")

            # Step 1: Parallel search for all queries
            search_tasks = [
                self.searcher.search_raw(q, max_results=cfg.max_results_per_query)
                for q in queries
            ]
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            # Step 2: Gathering unique links and filtering duplicates
            unique_links = {}
            for res in search_results:
                if isinstance(res, Exception) or not res:
                    continue

                for item in res:
                    url = item.get("href")
                    title = item.get("title", "Unknown Title")
                    # Protection against duplicates
                    if url and url not in unique_links:
                        unique_links[url] = title

            if not unique_links:
                return SkillResult.fail(
                    "Failed to find any useful links for the specified queries."
                )

            # Step 3: Limit the number of pages to read
            urls_to_read = list(unique_links.keys())[: cfg.max_pages_to_read]

            # Step 4: Parallel reading of pages
            read_tasks = [self.reader.read_raw(url) for url in urls_to_read]
            read_results = await asyncio.gather(*read_tasks, return_exceptions=True)

            # Step 5: Formatting result
            # Dynamically truncate each page so that total text volume doesn't exceed the agent's context limits.
            chars_per_page = max(2000, cfg.total_max_chars // len(urls_to_read))

            final_blocks = []
            for i, url in enumerate(urls_to_read):
                title = unique_links[url]
                content = read_results[i]

                # Skip pages that returned an error
                if isinstance(content, Exception) or not content:
                    continue

                content_str = str(content)
                truncated_content = truncate_text(
                    content_str,
                    chars_per_page,
                    "... [Text truncated to save context]",
                )

                block = f"### Title: {title}\nURL: {url}\n\n{truncated_content}\n"
                final_blocks.append(block)

            if not final_blocks:
                return SkillResult.fail(
                    "Links found, but failed to extract text from any of the pages (anti-scraping protection possible)."
                )

            # Add a single general log entry to the agent's browser history
            queries_str = ", ".join(queries)
            self.client.state.add_history(f"Deep Research: {queries_str}")

            main_logger.info(
                f"[Web] deep_research successfully completed (read {len(final_blocks)} pages)."
            )

            return SkillResult.ok("\n\n---\n\n".join(final_blocks))

        except Exception as e:
            return SkillResult.fail(f"Critical error during deep_research: {e}")

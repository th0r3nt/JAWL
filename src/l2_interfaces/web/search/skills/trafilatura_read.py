"""
Trafilatura page reader engine (Strategy).

Extracts clean formatted text locally without third-party services.
"""

import asyncio
import trafilatura

from src.utils.logger import main_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.web.search.client import WebSearchClient

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents


class TrafilaturaReader:
    """Local webpage extractor via Trafilatura."""

    def __init__(self, client: WebSearchClient):
        self.client = client

    async def read_raw(self, url: str) -> str | None:
        def _fetch():
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            return trafilatura.extract(
                downloaded, include_links=True, include_images=False, include_formatting=True
            )

        return await asyncio.to_thread(_fetch)

    @skill(swarm=[Subagents.WEB_RESEARCHER])
    async def read_webpage(self, url: str) -> SkillResult:
        """
        Reads webpage content.
        """

        try:
            text = await self.read_raw(url)
            if not text:
                return SkillResult.fail(f"Error: failed to read {url} (captcha or no text).")

            total_len = len(text)
            if total_len > self.client.max_page_chars:
                text = truncate_text(text, self.client.max_page_chars, "... [Truncated]")
                main_logger.info(f"[Web] Page read (Trafilatura, with truncation): {url}")
            else:
                main_logger.info(f"[Web] Page read (Trafilatura, entirely): {url}")

            header = (
                f"[Webpage (Trafilatura) | Read: {len(text)}/{total_len} chars]\n{'='*40}\n"
            )
            self.client.state.add_history(f"Reading page: {url}")
            return SkillResult.ok(header + text)

        except Exception as e:
            return SkillResult.fail(f"Page parsing error: {e}")

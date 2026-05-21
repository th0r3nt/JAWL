"""
Jina page reader engine (Strategy).

Excellent at bypassing captchas and anti-fraud systems, returning clean Markdown.
"""

import asyncio
import urllib.request
import urllib.error
from typing import Optional

from src import __version__
from src.utils.logger import main_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.web.search.client import WebSearchClient
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents


class JinaReader:
    """Webpage content parser via r.jina.ai API."""

    def __init__(self, client: WebSearchClient) -> None:
        self.client = client

    async def read_raw(self, url: str) -> Optional[str]:
        """
        Internal method for reading text (used by DeepResearch).
        """

        def _fetch() -> str:
            req_url = f"https://r.jina.ai/{url}"
            req = urllib.request.Request(req_url)
            req.add_header("User-Agent", f"JAWL-Agent/{__version__}")

            with urllib.request.urlopen(req, timeout=self.client.timeout) as response:
                return response.read().decode("utf-8", errors="replace")

        return await asyncio.to_thread(_fetch)

    @skill(swarm=[Subagents.WEB_RESEARCHER])
    async def read_webpage(self, url: str) -> SkillResult:
        """
        Reads webpage content.
        """

        try:
            text = await self.read_raw(url)
            if not text:
                return SkillResult.fail(
                    f"Error: failed to read {url} (empty response from Jina)."
                )

            total_len = len(text)
            if total_len > self.client.max_page_chars:
                text = truncate_text(text, self.client.max_page_chars, "... [Truncated]")
                main_logger.info(f"[Web] Page read (Jina, with truncation): {url}")
            else:
                main_logger.info(f"[Web] Page read (Jina, entirely): {url}")

            header = f"[Webpage (Jina) | Read: {len(text)}/{total_len} chars]\n{'='*40}\n"
            self.client.state.add_history(f"Reading page (Jina): {url}")
            return SkillResult.ok(header + text)

        except urllib.error.HTTPError as e:
            return SkillResult.fail(f"HTTP Error reading {url}: {e.code} {e.reason}")

        except Exception as e:
            return SkillResult.fail(f"Page parsing error (Jina): {e}")

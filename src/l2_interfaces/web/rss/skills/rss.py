"""
Skills for reading Atom/RSS news feeds.

Allows the agent to extract clean content (Summary/Description) without navigating to original sites.
"""

from src.utils.logger import main_logger
from src.utils._tools import truncate_text, clean_html
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.rss.client import WebRSSClient


class WebRSSSkills:
    """Skills for reading RSS/Atom feeds."""

    def __init__(self, client: WebRSSClient):
        self.client = client

    @skill()
    async def list_feeds(self) -> SkillResult:
        """
        Lists tracked RSS feeds.
        """

        if not self.client.config.feeds:
            return SkillResult.ok("List of saved RSS feeds is empty.")

        lines = ["Available RSS feeds:"]
        for feed in self.client.config.feeds:
            lines.append(f"- Name: '{feed.name}' | URL: {feed.url}")

        return SkillResult.ok("\n".join(lines))

    @skill()
    async def read_feed(self, url: str, limit: int = 5) -> SkillResult:
        """
        Reads XML RSS/Atom feed.
        """

        try:
            feed = await self.client.fetch_feed(url)

            if feed.bozo:
                main_logger.warning(
                    f"[Web] Feed {url} has formatting errors but will be partially parsed."
                )

            if not feed.entries:
                return SkillResult.ok(
                    f"Feed at '{url}' is empty, unavailable, or contains no entries."
                )

            limit = max(1, min(limit, 20))  # Protection against context overflow
            lines = [f"Latest publications from '{url}':"]

            for entry in feed.entries[:limit]:
                title = clean_html(entry.get("title", "Untitled"))
                link = entry.get("link", "No link")
                date = entry.get("published", entry.get("updated", "Unknown date"))

                # Extract summary and clean with a powerful HTML tags stripper
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                summary = truncate_text(summary, max_chars=400, suffix="...")

                lines.append(
                    f"### {title}\n* Date: {date}\n* URL: {link}\n* Summary: {summary}\n"
                )

            main_logger.info(f"[Web] Feed '{url}' read ({len(feed.entries[:limit])} entries).")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error reading feed '{url}': {e}")

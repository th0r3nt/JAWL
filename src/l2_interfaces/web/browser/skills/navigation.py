"""
Browser navigation skills.

Handles page loading, scrolling, and browser shutdown.
"""

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.browser.client import WebBrowserClient


class BrowserNavigation:
    """
    Skills for tab management and browsing navigation.
    """

    def __init__(self, client: WebBrowserClient):
        self.client = client

    @skill()
    async def navigate(self, url: str) -> SkillResult:
        """
        Navigates to or refreshes URL.
        """

        try:
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            await self.client.ensure_browser()
            self.client.touch()

            await self.client.page.goto(url, wait_until="networkidle")
            await self.client.update_state_view()

            self.client.state.add_history(f"Navigated to: {url}")
            main_logger.info(f"[Web Browser] Navigation to URL: {url}")

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error loading page: {e}")

    @skill()
    async def scroll(self, direction: str = "down") -> SkillResult:
        """
        Scrolls page up/down by one viewport.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            sign = "" if direction == "down" else "-"
            # JS-injection to scroll by viewport height
            await self.client.page.evaluate(f"window.scrollBy(0, {sign}window.innerHeight)")

            # Give time for lazy-loaded images/DOM to load
            await self.client.page.wait_for_timeout(1000)
            await self.client.update_state_view()

            self.client.state.add_history(f"Scroll: {direction}")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Scroll error: {e}")

    @skill()
    async def close(self) -> SkillResult:
        """
        Closes browser.
        """

        try:
            await self.client.close_browser()
            self.client.state.add_history("Browser closed.")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error closing browser: {e}")

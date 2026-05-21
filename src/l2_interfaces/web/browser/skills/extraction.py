"""
Browser extraction skills.

Allows the agent to capture screenshots and extract clean text from pages.
"""

import asyncio
from src.utils.logger import main_logger
from src.utils._tools import truncate_text, validate_sandbox_path, draw_image_grid
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.browser.client import WebBrowserClient


class BrowserExtraction:
    """
    Skills for extracting information from the page (screenshots, raw text).
    """

    def __init__(self, client: WebBrowserClient):
        self.client = client

    @skill()
    async def take_screenshot(
        self,
        filename: str,
        with_grid: bool = True,
        grid_step: int = 100,
        full_page: bool = False,
    ) -> SkillResult:
        """
        Captures and injects page screenshot into context.

        with_grid: Overlays coordinate grid.
        grid_step: Grid interval (40 for higher precision).
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            if "/" not in filename and "\\" not in filename:
                filename = f"sandbox/_system/download/{filename}"

            safe_path = validate_sandbox_path(filename)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # Capture screenshot
            await self.client.page.screenshot(path=str(safe_path), full_page=full_page)

            # Apply coordinate grid
            if with_grid:
                await asyncio.to_thread(draw_image_grid, safe_path, grid_step)

            self.client.state.add_history(f"Screenshot: {safe_path.name} (Grid: {with_grid})")
            main_logger.info(f"[Web Browser] Screenshot taken: {safe_path.name}")

            marker = f"[SYSTEM_MARKER_IMAGE_ATTACHED: {safe_path.resolve()}]"
            return SkillResult.ok(
                f"{marker}: True. Screenshot taken and is already in your visual context. "
                f"Saved to: sandbox/{filename}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error creating screenshot: {e}")

    @skill()
    async def extract_text(self) -> SkillResult:
        """
        Extracts all text from current page.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            # JS-injection to get clean text from body
            text = await self.client.page.evaluate("document.body.innerText")

            if not text or not text.strip():
                return SkillResult.fail("No text content found on the page.")

            clean_text = truncate_text(text.strip(), 20000, "... [Text truncated]")

            self.client.state.add_history("Raw text extraction")
            return SkillResult.ok(f"Page text:\n\n{clean_text}")

        except Exception as e:
            return SkillResult.fail(f"Error extracting text: {e}")

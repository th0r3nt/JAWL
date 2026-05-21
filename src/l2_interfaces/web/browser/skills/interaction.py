"""
Skills for physical interaction with the loaded webpage in the browser.

Allow clicking, typing, and hovering (including by absolute pixel coordinates).
"""

from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.browser.client import WebBrowserClient


class BrowserInteraction:
    """
    Skills for physical interaction with page elements (clicks, input, keyboard).
    """

    def __init__(self, client: WebBrowserClient):
        self.client = client

    @skill()
    async def click(self, role: str, name: str) -> SkillResult:
        """
        Clicks element by ARIA role.

        role: ARIA role (e.g., 'link', 'button').
        name: Internal name or text.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            locator = self.client.page.get_by_role(role, name=name, exact=True).first
            await locator.click()

            # Wait for potential network requests after click (e.g., SPA loading)
            try:
                await self.client.page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            await self.client.update_state_view()
            await self.client.save_session()

            self.client.state.add_history(f"Click: [{role}] '{name}'")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(
                f"Failed to click the element (perhaps it is overlapped or not found): {e}"
            )

    @skill()
    async def hover(self, role: str, name: str) -> SkillResult:
        """
        Hovers cursor over element.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            locator = self.client.page.get_by_role(role, name=name, exact=True).first
            await locator.hover()

            # Wait for menu appearance animation
            await self.client.page.wait_for_timeout(1000)
            await self.client.update_state_view()

            self.client.state.add_history(f"Hover: [{role}] '{name}'")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Failed to hover cursor over the element: {e}")

    @skill()
    async def fill_text(self, role: str, name: str, text: str) -> SkillResult:
        """
        Inputs text into a field.
        E.g.: role="textbox", name="Username", text="admin".
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            locator = self.client.page.get_by_role(role, name=name, exact=True).first
            await locator.fill(text)

            await self.client.update_state_view()
            self.client.state.add_history(f"Text filled in: [{role}] '{name}'")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Failed to input text: {e}")

    @skill()
    async def press_key(self, key: str) -> SkillResult:
        """
        Presses keyboard key (e.g., 'Enter', 'Escape').
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            await self.client.page.keyboard.press(key)

            try:
                await self.client.page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

            await self.client.update_state_view()
            self.client.state.add_history(f"Key pressed: {key}")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error pressing key: {e}")

    @skill()
    async def click_coordinates(self, x: int, y: int) -> SkillResult:
        """
        Clicks specified page coordinates.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            # Scroll the page so that the element is guaranteed to be in the viewport (center it)
            scroll_x = max(0, x - 500)
            scroll_y = max(0, y - 300)
            await self.client.page.evaluate(
                f"window.scrollTo({{left: {scroll_x}, top: {scroll_y}, behavior: 'instant'}})"
            )
            await self.client.page.wait_for_timeout(500)

            # Calculate coordinates relative to the current viewport for the mouse click
            viewport_x = await self.client.page.evaluate(f"{x} - window.scrollX")
            viewport_y = await self.client.page.evaluate(f"{y} - window.scrollY")

            # Click
            await self.client.page.mouse.click(viewport_x, viewport_y)

            try:
                await self.client.page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

            await self.client.update_state_view()
            await self.client.save_session()

            self.client.state.add_history(f"Click at coordinates: ({x}, {y})")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Failed to click coordinates: {e}")

    @skill()
    async def hover_coordinates(self, x: int, y: int) -> SkillResult:
        """
        Hovers cursor over page coordinates.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            scroll_x = max(0, x - 500)
            scroll_y = max(0, y - 300)
            await self.client.page.evaluate(
                f"window.scrollTo({{left: {scroll_x}, top: {scroll_y}, behavior: 'instant'}})"
            )
            await self.client.page.wait_for_timeout(500)

            viewport_x = await self.client.page.evaluate(f"{x} - window.scrollX")
            viewport_y = await self.client.page.evaluate(f"{y} - window.scrollY")

            await self.client.page.mouse.move(viewport_x, viewport_y)
            await self.client.page.wait_for_timeout(1000)

            await self.client.update_state_view()

            self.client.state.add_history(f"Hover at coordinates: ({x}, {y})")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Failed to hover cursor: {e}")

    @skill()
    async def type_text(self, text: str) -> SkillResult:
        """
        Types text into focused element.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            await self.client.page.keyboard.type(text)

            try:
                await self.client.page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

            await self.client.update_state_view()
            self.client.state.add_history("Keyboard text input")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error during text input: {e}")

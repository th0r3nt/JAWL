"""
Stateful manager of the Headless Browser (Playwright).

Provides "lazy" initialization of the Chromium process to save RAM when the agent is not searching.
Manages the storage state (Cookies, Local Storage) to bypass repeated authorizations on websites.
Converts the DOM into lightweight Markdown (AOM).
"""

import time
import sys
import asyncio
import urllib.parse
from pathlib import Path
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from src.utils.logger import main_logger
from src.utils._tools import truncate_text
from src.utils.settings import WebBrowserConfig
from src.l2_interfaces.web.browser.state import WebBrowserState


class WebBrowserClient:
    """
    Stateful client for managing Playwright.
    Supports lazy loading and session persistence (cookies).
    """

    def __init__(
        self,
        state: WebBrowserState,
        config: WebBrowserConfig,
        data_dir: Path,
        proxy_url: Optional[str] = None,
    ) -> None:
        """
        Initializes the browser manager.

        Args:
            state: L0 State (dashboard).
            config: Browser configuration (headless, timeouts).
            data_dir: Local data root directory.
        """

        self.state = state
        self.config = config

        self.profile_dir = data_dir / "interfaces" / "web" / "browser_profile"
        self.state_file = self.profile_dir / "storage_state.json"
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self.last_activity_time: float = time.time()
        self._lock = asyncio.Lock()

        self.proxy_url = proxy_url

    async def start(self) -> None:
        """Called at system startup (the browser is not physically launched until the first request)."""
        self.state.is_online = True
        main_logger.info("[Web Browser] Interface is ready.")

    async def stop(self) -> None:
        """Correctly closes the browser on system shutdown."""
        await self.close_browser()
        self.state.is_online = False

    def touch(self) -> None:
        """
        Updates the activity timer for the Watchdog.
        """
        self.last_activity_time = time.time()

    async def ensure_browser(self) -> None:
        """
        Ensures the browser is running. Automatically downloads Chromium on
        the first run if binaries are missing on the host.
        """

        async with self._lock:
            if self.page and not self.page.is_closed():
                return

            if not self.playwright:
                self.playwright = await async_playwright().start()

            if not self.browser:
                try:
                    self.browser = await self.playwright.chromium.launch(
                        headless=self.config.headless
                    )
                except Exception as e:
                    # If Playwright complains about missing browsers, download them ourselves
                    if "playwright install" in str(e):
                        main_logger.info(
                            "[Web Browser] Chromium binaries not found. Starting automatic download (will take a couple of minutes)."
                        )

                        proc = await asyncio.create_subprocess_exec(
                            sys.executable,
                            "-m",
                            "playwright",
                            "install",
                            "chromium",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        await proc.communicate()

                        main_logger.info(
                            "[Web Browser] Chromium download completed. Launching browser."
                        )

                        # Retry launch after installation
                        self.browser = await self.playwright.chromium.launch(
                            headless=self.config.headless
                        )
                    else:
                        raise

            # Context configuration
            context_kwargs = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }

            # Configure proxy for Playwright
            if self.proxy_url:
                parsed = urllib.parse.urlparse(self.proxy_url)
                # Playwright accepts socks5://...
                scheme = "socks5" if parsed.scheme.startswith("socks") else parsed.scheme

                proxy_settings = {"server": f"{scheme}://{parsed.hostname}:{parsed.port}"}
                if parsed.username:
                    proxy_settings["username"] = parsed.username
                if parsed.password:
                    proxy_settings["password"] = parsed.password

                context_kwargs["proxy"] = proxy_settings

            # Restore the saved session (cookies, authorizations) if it exists
            if self.state_file.exists():
                context_kwargs["storage_state"] = str(self.state_file)

            self.context = await self.browser.new_context(**context_kwargs)
            self.page = await self.context.new_page()

            # Set the default timeout for all actions (in ms)
            self.page.set_default_timeout(self.config.timeout_sec * 1000)

            main_logger.info("[Web Browser] Chromium process launched.")

    async def save_session(self) -> None:
        """Saves cookies and Local Storage to disk (in state_file)."""
        if self.context:
            await self.context.storage_state(path=str(self.state_file))

    async def close_browser(self) -> None:
        """Correctly closes the browser and frees RAM."""
        async with self._lock:
            if self.context:
                await self.save_session()

            if self.browser:
                await self.browser.close()
                main_logger.info("[Web Browser] Chromium process stopped.")

            self.browser = None
            self.context = None
            self.page = None
            self.state.is_open = False
            self.state.viewport = "Browser is closed."

    async def update_state_view(self) -> None:
        """
        Converts the DOM tree of the current webpage into a flat AOM (Accessibility Object Model)
        YAML structure (via aria_snapshot). Filters out visual noise, leaving the agent only
        text and clickable (interactive) elements.
        """
        if not self.page or self.page.is_closed():
            self.state.is_open = False
            self.state.viewport = "Browser is closed."
            return

        self.state.is_open = True
        self.state.current_url = self.page.url
        self.state.page_title = await self.page.title()

        try:
            # aria_snapshot is perfect for AI agents (returns clean, lightweight YAML)
            snapshot = await self.page.locator("body").aria_snapshot()

            if snapshot:
                # Protect against context overflow (for huge pages)
                self.state.viewport = truncate_text(
                    snapshot,
                    15000,
                    "...[The page is too long and has been truncated. For further viewing - scroll]",
                )
            else:
                self.state.viewport = (
                    "Element tree is empty (perhaps the page has not loaded yet)."
                )
        except Exception as e:
            self.state.viewport = f"Error building accessibility tree: {e}"

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Agent context provider.
        """

        desc = "Description: browser (Playwright) for interactive webpages."
        if not self.state.is_online:
            return f"### WEB BROWSER [OFF]\n{desc}\nThe interface is disabled."

        if not self.state.is_open:
            return f"### WEB BROWSER [ON]\n{desc}\nThe browser is closed."

        history_str = (
            "\n".join(f"  - {h}" for h in self.state.history)
            if self.state.history
            else "  Empty"
        )

        return f"""### WEB BROWSER [ON]
{desc}
* Current tab: {self.state.page_title}
* URL: {self.state.current_url}
* Recent actions:
{history_str}

* Visible AOM-elements:
{self.state.viewport}
"""

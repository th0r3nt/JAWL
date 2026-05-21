"""
Background Browser Watchdog.

Monitors idle time. If the agent opened the browser and forgot to close it,
the Watchdog will automatically kill the Chromium process to free RAM.
"""

import asyncio
import time
from typing import Optional
from src.utils.logger import main_logger
from src.l2_interfaces.web.browser.client import WebBrowserClient


class WebBrowserEvents:
    """
    RAM Watchdog. Closes the browser after prolonged idle time.
    """

    def __init__(self, client: WebBrowserClient) -> None:
        self.client = client
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starts the Watchdog."""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stops the Watchdog."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        """Browser idle checking loop."""
        while self._is_running:
            try:
                # If the browser is open, check the idle timer
                if self.client.page and not self.client.page.is_closed():
                    idle_time = time.time() - self.client.last_activity_time

                    if idle_time > self.client.config.idle_timeout_sec:
                        main_logger.info(
                            f"[Web Browser] Browser was not used for {int(idle_time)} sec. Auto-closing to free RAM."
                        )
                        await self.client.close_browser()

            except asyncio.CancelledError:
                break

            except Exception as e:
                main_logger.error(f"[Web Browser] Error in Watchdog: {e}")

            await asyncio.sleep(60)  # Check once per minute

"""
Background listener/worker (Events Poller) of the custom interface.

This module runs in the background (asynchronous infinite loop) and waits for incoming events
from the external world. When an event occurs, the worker publishes it to `EventBus`,
causing the agent to wake up faster.
"""

import asyncio
from typing import Optional, Any

from src.utils.logger import main_logger
from src.utils.event.bus import EventBus

# In real code, you need to register your event (e.g., EXAMPLE_INCOMING)
# in src/utils/event/registry.py (declare EXAMPLE_INCOMING event in Events)
# from src.utils.event.registry import Events


class ExampleEvents:
    """Event listener (Webhooks, Long Polling, WebSockets)."""

    def __init__(self, client: Any, event_bus: EventBus) -> None:
        self.client = client
        self.bus = event_bus
        self._is_running = False
        self._polling_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starts the background polling process."""
        if self._is_running:
            return

        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        main_logger.info("[Example] Background worker started.")

    async def stop(self) -> None:
        """Stops the background process."""
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        main_logger.info("[Example] Background worker stopped.")

    async def _loop(self) -> None:
        """
        Infinite loop that polls the API or waits for data from a socket.
        """
        while self._is_running:
            try:
                # 1. Request to the server through the client
                # new_data = await self.client.fetch_new_data()
                new_data = None  # Placeholder

                if new_data:
                    # 2. Be sure to update L0 State so the agent can read it in context
                    # self.client.state.last_data = new_data

                    # 3. Publish the event to the bus (wake up the agent)
                    # await self.bus.publish(
                    #     Events.EXAMPLE_INCOMING,
                    #     message="New event from service",
                    #     payload_data=new_data
                    # )
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                main_logger.error(f"[Example] Error in background loop: {e}")

            # Be sure to pause so as not to block the main Event Loop completely
            await asyncio.sleep(60)

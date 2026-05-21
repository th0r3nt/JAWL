"""
Background timekeeper (Time Watchdog).

Compares the current UNIX-timestamp with scheduled tasks. Upon match —
generates a system event in EventBus, urgently waking the agent
and passing the details of the triggered alarm.
"""

import time
import asyncio
from typing import Optional

from src.utils.logger import main_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l2_interfaces.calendar.state import CalendarState
from src.l2_interfaces.calendar.client import CalendarClient


class CalendarEvents:
    """
    Background polling of calendar events.
    Compares current time with trigger_at. If triggered — wakes the agent.
    """

    def __init__(
        self,
        client: CalendarClient,
        state: CalendarState,
        event_bus: EventBus,
        polling_interval: int,
    ) -> None:
        """
        Initializes the timekeeper.

        Args:
            client: CalendarClient instance.
            state: L0 state (dashboard).
            event_bus: Global event bus.
            polling_interval: How often to check timers (in seconds).
        """
        self.client = client
        self.state = state
        self.bus = event_bus
        self.polling_interval = polling_interval

        self._is_running: bool = False
        self._polling_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starts background polling of calendar events."""
        if self._is_running:
            return

        self._is_running = True
        self.client.state.is_online = True
        self.client.update_state_view()  # Trigger updated method from client

        self._polling_task = asyncio.create_task(self._loop())
        main_logger.info("[Calendar] Background time monitoring started.")

    async def stop(self) -> None:
        """Stops background polling of calendar events."""
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

        self.client.state.is_online = False
        main_logger.info("[Calendar] Background time monitoring stopped.")

    async def _loop(self) -> None:
        """Infinite loop checking timers."""
        while self._is_running:
            try:
                now = time.time()
                events = self.client.get_all_events()
                modified = False
                active_events = []

                for ev in events:
                    if now >= ev["trigger_at"]:
                        # Publish event to the agent, wake them up
                        await self.bus.publish(
                            Events.SYSTEM_CALENDAR_ALARM,
                            alarm_id=ev["id"],
                            title=ev["title"],
                            type=ev["type"],
                        )
                        modified = True

                        # Update timer or delete
                        if ev["type"] == "one_time":
                            continue  # Skip adding to active_events (delete)

                        elif ev["type"] == "interval":
                            ev["trigger_at"] += ev["interval_minutes"] * 60
                            active_events.append(ev)

                        elif ev["type"] == "recurring":
                            # Add needed number of days
                            ev["trigger_at"] += ev["interval_days"] * 86400
                            active_events.append(ev)
                    else:
                        active_events.append(ev)

                # If at least one timer triggered, overwrite JSON
                # Client's _save() method inside update_events will automatically update the state
                if modified:
                    self.client.update_events(active_events)

            except asyncio.CancelledError:
                break
            except Exception as e:
                main_logger.error(f"[Calendar] Error in monitoring loop: {e}")

            await asyncio.sleep(self.polling_interval)

"""
Agent Lifecycle and Rhythm (Pulse) Orchestrator.

Responsible for scheduling ReAct reasoning loops, capturing external events
from the EventBus, and dynamically adjusting sleep intervals (Event Acceleration).
"""

import asyncio
import time
from collections import deque
from typing import Optional, Dict, Any, TYPE_CHECKING

from src.utils.logger import main_logger, agent_logger
from src.utils.event.registry import EventLevel
from src.utils.dtime import get_now_formatted
from src.utils._tools import update_last_active_time

if TYPE_CHECKING:
    from src.l3_agent.react.loop import ReactLoop
    from src.utils.settings import EventAccelerationConfig


class Heartbeat:
    """
    Main agent pulse orchestrator.
    Manages reasoning loop invocation schedules and triggers wakeups.
    """

    def __init__(
        self,
        react_loop: "ReactLoop",
        heartbeat_interval: int,
        continuous_cycle: bool,
        accel_config: "EventAccelerationConfig",
        timezone: int,
    ) -> None:
        """
        Initializes the heartbeat orchestrator.

        Args:
            react_loop: Active reasoning loop instance.
            heartbeat_interval: Base sleep interval in seconds.
            continuous_cycle: Continuous execution flag without sleep.
            accel_config: Wakeup acceleration multipliers configuration.
            timezone: Timezone UTC offset.
        """

        self.react_loop = react_loop
        self.heartbeat_interval = heartbeat_interval
        self.continuous_cycle = continuous_cycle
        self.accel_config = accel_config
        self.timezone = timezone

        self._wake_event = asyncio.Event()
        self._is_running: bool = False

        self._next_tick_time: float = 0.0
        self._wake_reason: str = "HEARTBEAT"
        self._wake_payload: Dict[str, Any] = {}
        self._wake_level: int = 0

        self._sleep_memory: deque[Dict[str, Any]] = deque(maxlen=20)

        self._active_react_task: Optional[asyncio.Task] = None

        self._is_interrupted: bool = False

    def answer_to_event(
        self, level: EventLevel, event_name: str, payload: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Analyzes incoming events and schedules/accelerates wakeups.

        Args:
            level: Event severity level.
            event_name: Triggering event name identifier.
            payload: Event parameters.
        """

        now = time.time()
        payload = payload or {}
        time_str = get_now_formatted(self.timezone, fmt="%H:%M:%S")

        event_data = {
            "time": time_str,
            "level": level.name,
            "name": event_name,
            "payload": payload,
        }

        # Determine event level multiplier
        multiplier = 1.0
        if level == EventLevel.CRITICAL:
            multiplier = self.accel_config.critical_multiplier

        elif level == EventLevel.HIGH:
            multiplier = self.accel_config.high_multiplier

        elif level == EventLevel.MEDIUM:
            multiplier = self.accel_config.medium_multiplier

        elif level == EventLevel.LOW:
            multiplier = self.accel_config.low_multiplier

        elif level == EventLevel.BACKGROUND:
            multiplier = self.accel_config.background_multiplier

        is_awake = self._active_react_task and not self._active_react_task.done()

        # ---------------------------------------------------------------------
        # Logic for currently active (awake) agent
        # ---------------------------------------------------------------------

        if is_awake:
            # Inject event directly into the active cycle
            self.react_loop.add_realtime_event(event_data)

            log = f"[Heartbeat] Incoming event '{event_name}' ({level.name}) received during agent execution. Data appended to context."
            agent_logger.info(log)

            # If multiplier is 0.0, perform a hard interruption
            if multiplier <= 0.01:
                log = f"[Heartbeat] Interrupted current ReAct cycle due to event: {event_name} ({level.name})"
                agent_logger.warning(log)

                self._wake_reason = event_name
                self._wake_payload = payload
                self._wake_level = level.value
                self._is_interrupted = True

                # Set timer to zero to restart the cycle immediately after cancel()
                self._next_tick_time = time.time()
                self._wake_event.set()

                self._active_react_task.cancel()

            return

        # ---------------------------------------------------------------------
        # Logic for currently sleeping agent
        # ---------------------------------------------------------------------

        self._sleep_memory.append(event_data)

        remaining = self._next_tick_time - now

        if multiplier < 1.0:
            safe_remaining = max(0.0, remaining)

            new_remaining = safe_remaining * multiplier
            reduced_by = safe_remaining - new_remaining

            self._next_tick_time = now + new_remaining
            self._wake_event.set()

            # If remaining sleep is cut to zero, execute urgent wakeup
            if new_remaining <= 0.01:
                # Override primary reason only if the new event is of equal or higher priority
                if level.value >= self._wake_level:
                    log = f"[Heartbeat] Incoming wakeup event: '{event_name}' ({level.name}). Invoking LLM."
                    agent_logger.info(log)

                    self._wake_reason = event_name
                    self._wake_payload = payload
                    self._wake_level = level.value
                else:
                    log = f"[Heartbeat] Incoming event: '{event_name}' ({level.name}). Sleep already interrupted by a higher priority event."
                    agent_logger.info(log)
            else:
                if safe_remaining > 0:
                    log = f"[Heartbeat] Incoming event: '{event_name}' ({level.name}). Next LLM execution scheduled sooner by {reduced_by:.1f} sec. Until wakeup: {new_remaining:.1f} sec."
                    agent_logger.info(log)

    async def start(self) -> None:
        """
        Starts the heartbeat infinite polling loop.
        """
        if self._is_running:
            return

        self._is_running = True
        log = "[Heartbeat] Agent switched to autonomous mode."
        agent_logger.info(log)

        if self._next_tick_time == 0.0:
            self._next_tick_time = time.time() + self.heartbeat_interval

        update_last_active_time()

        while self._is_running:
            update_last_active_time()
            now = time.time()

            if self.continuous_cycle:
                await asyncio.sleep(0.1)
            else:
                sleep_duration = self._next_tick_time - now
                if sleep_duration > 0:
                    self._wake_event.clear()
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=sleep_duration)
                    except asyncio.TimeoutError:
                        if self._next_tick_time <= time.time():
                            self._wake_reason = "HEARTBEAT"
                            self._wake_payload = {}

            if self.continuous_cycle or time.time() >= self._next_tick_time:
                missed_events = list(self._sleep_memory)
                self._sleep_memory.clear()

                if self._wake_reason != "HEARTBEAT":
                    for i in range(len(missed_events) - 1, -1, -1):
                        if (
                            missed_events[i]["name"] == self._wake_reason
                            and missed_events[i]["payload"] == self._wake_payload
                        ):
                            missed_events.pop(i)
                            break

                self._next_tick_time = time.time() + self.heartbeat_interval

                try:
                    self._active_react_task = asyncio.create_task(
                        self.react_loop.run(
                            event_name=self._wake_reason,
                            payload=self._wake_payload,
                            missed_events=missed_events,
                        )
                    )
                    await self._active_react_task
                    self._wake_reason = "HEARTBEAT"
                    self._wake_payload = {}
                    
                except asyncio.CancelledError:
                    if self._is_interrupted:
                        main_logger.info(
                            "[System] Current ReAct cycle successfully cancelled."
                        )
                        self._is_interrupted = False
                    else:
                        raise
                except Exception as e:
                    log = f"[System] Critical error in ReAct reasoning cycle: {e}"
                    agent_logger.error(log)
                    self._next_tick_time = time.time() + self.heartbeat_interval
                    self._wake_reason = "HEARTBEAT"
                    self._wake_payload = {}
                finally:
                    self._active_react_task = None

    def stop(self) -> None:
        """Terminates heartbeat loop and cancels any running ReAct cycles."""
        self._is_running = False
        self._wake_event.set()
        if self._active_react_task and not self._active_react_task.done():
            self._is_interrupted = True
            self._active_react_task.cancel()

        log = "[Heartbeat] Orchestrator stopped."
        agent_logger.info(log)

    def update_config(self, key: str, value: Any) -> None:
        """
        Hot-reloads heartbeat parameters from EventBus.

        Args:
            key: Config parameter key.
            value: Value payload.
        """
        if key == "heartbeat_interval":
            self.heartbeat_interval = int(value)

            log = f"[System] Heartbeat updated interval to {self.heartbeat_interval} sec."
            agent_logger.info(log)

        elif key == "continuous_cycle":
            self.continuous_cycle = bool(value)

            log = f"[System] Heartbeat updated continuous_cycle to {self.continuous_cycle}."
            agent_logger.info(log)

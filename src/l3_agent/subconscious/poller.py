"""
Subconscious Poller.

Tracks ticks (wakeup steps) of the main agent and fires triggers
to launch subconscious background patterns according to configured schedules.
Synchronizes tick progress metrics with L0 State.
"""

from typing import Dict
from src.utils.logger import subc_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import SubconsciousConfig
from src.l0_state.agent.state import AgentState
from src.l3_agent.subconscious.schema import Pattern


class SubconsciousPoller:
    """Quiet tick counter. Runs in the background and wakes up the subconscious on schedule."""

    def __init__(
        self, agent_state: AgentState, event_bus: EventBus, config: SubconsciousConfig
    ) -> None:
        """
        Initializes the poller and immediately synchronizes limits with L0 State.
        """

        self.agent_state = agent_state
        self.bus = event_bus
        self.config = config

        self.counters: Dict[Pattern, int] = {p: 0 for p in Pattern}

        self._update_state_counters()

    def _update_state_counters(self) -> None:
        """
        Compiles nested dictionary of limit counters and broadcasts it to L0.
        """
        
        cfg_patterns = self.config.patterns
        limits_map = {
            Pattern.CONSOLIDATION: cfg_patterns.consolidation,
            Pattern.REFLECTION: cfg_patterns.reflection,
            Pattern.FORGETTING: cfg_patterns.forgetting,
        }

        state_counters = {}
        for pattern, p_config in limits_map.items():
            if not p_config.enabled:
                continue
            state_counters[pattern.value] = {
                "current": self.counters[pattern],
                "limit": p_config.activation_limit_ticks,
            }
        self.agent_state.subconscious_counters = state_counters

    async def on_tick_saved(self, **kwargs) -> None:
        """
        Handler for the REACT_TICK_SAVED event.
        Increments counters and dispatches wakeup triggers on limit matches.
        """

        if not self.config.enabled:
            return

        cfg_patterns = self.config.patterns

        limits = {
            Pattern.CONSOLIDATION: cfg_patterns.consolidation,
            Pattern.REFLECTION: cfg_patterns.reflection,
            Pattern.FORGETTING: cfg_patterns.forgetting,
        }

        triggered_patterns = []

        for pattern, p_config in limits.items():
            if not p_config.enabled:
                continue

            self.counters[pattern] += 1

            if self.counters[pattern] >= p_config.activation_limit_ticks:
                self.counters[pattern] = 0
                triggered_patterns.append(pattern)

        self._update_state_counters()

        for pattern in triggered_patterns:
            log = f"[Subconscious] Pattern '{pattern.value.upper()}' reached tick limit. Dispatching trigger."
            subc_logger.info(log)

            await self.bus.publish(Events.SUBCONSCIOUS_TRIGGERED, pattern=pattern)

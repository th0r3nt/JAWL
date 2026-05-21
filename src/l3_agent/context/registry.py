"""
Context Providers Registry (DI Container for L0 State).

Provides loose coupling between architectural layers. L2 interfaces register
their callback methods (providers) here, while the ContextBuilder (L3) asynchronously
polls them in a strict order defined by `ContextSection`.
"""

import asyncio
from enum import IntEnum
from typing import Callable, Awaitable, Any, Dict, List

from src.utils.logger import agent_logger


class ContextSection(IntEnum):
    """
    Defines a strict sequence of blocks inside the system prompt.
    Lower values correspond to higher priorities for the LLM Attention mechanism.
    """

    # Personality and internal state
    DRIVES = 10
    TRAITS = 20
    SKILLS = 30
    AGENT_STATE = 40
    HYPOTHESES = 48
    NOTES = 45

    # Universal block for active L2 interfaces
    INTERFACES = 50

    # Long-term memory
    MENTAL_STATES = 110
    TASKS = 120
    RAG_MEMORIES = 130

    # Recent ticks history (episodic memory)
    RECENT_TICKS = 140

    # Monte Carlo thoughts tree (ToT simulation)
    TREE_OF_THOUGHTS = 150

    # Primary wakeup trigger and background log
    HEARTBEAT = 160


class ContextRegistry:
    """Global registry of context provider callbacks."""

    def __init__(self) -> None:
        self._providers: Dict[str, Dict[str, Any]] = {}

    def register_provider(
        self, name: str, provider_func: Callable[..., Awaitable[str]], section: ContextSection
    ) -> None:
        """
        Registers an async function designed to yield a Markdown context block.

        Args:
            name: Unique identifier of the provider (e.g., "host_os").
            provider_func: Callback coroutine.
            section: Position in the hierarchy (ContextSection).
        """

        self._providers[name] = {"func": provider_func, "section": section}

        log = f"[System] Registered context provider: {name} (Section: {section.name})"
        agent_logger.debug(log)

    async def gather_all(
        self,
        event_name: str,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        agent_state: Any,
    ) -> Dict[str, str]:
        """
        Asynchronously polls all registered providers, returning their outputs sorted by priority.

        Args:
            event_name: Wakeup event name.
            payload: Wakeup event parameters dict.
            missed_events: Missed background events.
            agent_state: AgentState L0 instance.

        Returns:
            Dict[str, str]: Map of provider name to resolved Markdown block.
        """

        if not self._providers:
            return {}

        sorted_names = sorted(
            self._providers.keys(), key=lambda k: self._providers[k]["section"].value
        )

        tasks = [
            self._providers[name]["func"](
                event_name=event_name,
                payload=payload,
                missed_events=missed_events,
                agent_state=agent_state,
            )
            for name in sorted_names
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        context_blocks = {}
        for name, res in zip(sorted_names, results):
            if isinstance(res, Exception):
                log = f"[System] Context assembly error on provider '{name}': {res}"
                agent_logger.error(log)
                continue

            if res and isinstance(res, str):
                context_blocks[name] = res.strip()

        return context_blocks

"""
Main Subconscious Orchestrator.

Manages background cognitive processes (Consolidation, Reflection, Forgetting)
running parallel to the main ReAct reasoning loop.
"""

import asyncio
from typing import Any

from src.utils.logger import subc_logger
from src.utils.event.registry import Events
from src.utils.event.bus import EventBus
from src.utils.settings import SubconsciousConfig

from src.l0_state.agent.state import AgentState

from src.l1_databases.sql.manager import SQLManager
from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.graph.manager import GraphManager

from src.l3_agent.llm.executor import LLMExecutor

from src.l3_agent.subconscious.schema import Pattern
from src.l3_agent.subconscious.poller import SubconsciousPoller
from src.l3_agent.subconscious.runner import SubconsciousRunner


class SubconsciousOrchestrator:
    """Manages background cognitive activity of the agent."""

    def __init__(
        self,
        config: SubconsciousConfig,
        executor: LLMExecutor,
        sql_manager: SQLManager,
        vector_manager: VectorManager,
        graph_manager: GraphManager,
        event_bus: EventBus,
        agent_state: AgentState,
        root_dir: Any,
    ) -> None:
        self.config = config
        self.bus = event_bus

        self.poller = SubconsciousPoller(agent_state, event_bus, config)
        self.runner = SubconsciousRunner(
            executor=executor,
            model_name=config.llm_model,
            sql_manager=sql_manager,
            vector_manager=vector_manager,
            graph_manager=graph_manager,
            root_dir=root_dir,
        )

        # FIXED: Changed asyncio.semaphore to asyncio.Semaphore
        self._semaphores = {p: asyncio.Semaphore(1) for p in Pattern}
        self.background_tasks: set[asyncio.Task] = set()

    def setup_routing(self) -> None:
        """
        Subscribes to system events.
        """

        self.bus.subscribe(Events.REACT_TICK_SAVED, self.poller.on_tick_saved)
        self.bus.subscribe(Events.SUBCONSCIOUS_TRIGGERED, self._on_pattern_triggered)

    async def _on_pattern_triggered(self, **kwargs) -> None:
        """
        Captures the poller trigger and spawns the Runner in the background.
        """
        pattern = kwargs.get("pattern")
        if not pattern or not isinstance(pattern, Pattern):
            return

        task = asyncio.create_task(self._safe_run_pattern(pattern))
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def _safe_run_pattern(self, pattern: Pattern) -> None:
        """
        Semaphore wrapper to prevent database locks from parallel pattern execution.
        """
        
        if self._semaphores[pattern].locked():
            log = f"[Subconscious] Pattern {pattern.value.upper()} already running, skipping."
            subc_logger.debug(log)
            return

        async with self._semaphores[pattern]:
            try:
                limit = getattr(self.config.patterns, pattern.value).activation_limit_ticks
                await self.runner.run(pattern, ticks_to_analyze=limit)

            except Exception as e:
                log = f"[Subconscious] Critical error in pattern {pattern.value.upper()}: {e}"
                subc_logger.error(log)

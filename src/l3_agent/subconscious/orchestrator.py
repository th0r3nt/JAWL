"""
Главный Оркестратор Подсознания.
Связывает Poller, Runner и EventBus. Обрабатывает триггеры.
"""

import asyncio
from typing import Any

from src.utils.logger import main_logger, subc_logger
from src.utils.event.registry import Events
from src.utils.event.bus import EventBus
from src.utils.token_tracker import TokenTracker
from src.utils.settings import SubconsciousConfig

from src.l0_state.agent.state import AgentState

from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.manager import SQLManager
from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.graph.manager import GraphManager

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.subconscious.schema import Pattern
from src.l3_agent.subconscious.poller import SubconsciousPoller
from src.l3_agent.subconscious.runner import SubconsciousRunner


class SubconsciousOrchestrator:
    """Управляет фоновой когнитивной активностью агента."""

    def __init__(
        self,
        config: SubconsciousConfig,
        llm_client: LLMClient,
        sql_manager: SQLManager,
        vector_manager: VectorManager,
        graph_manager: GraphManager,
        sql_ticks: SQLTicks,
        token_tracker: TokenTracker,
        event_bus: EventBus,
        agent_state: AgentState,
        root_dir: Any,
    ) -> None:
        self.config = config
        self.bus = event_bus

        self.poller = SubconsciousPoller(agent_state, event_bus, config)
        self.runner = SubconsciousRunner(
            llm_client=llm_client,
            model_name=config.llm_model,
            sql_manager=sql_manager,
            vector_manager=vector_manager,
            graph_manager=graph_manager,
            token_tracker=token_tracker,
            root_dir=root_dir,
        )

        # Защита от race conditions (чтобы два процесса консолидации не бежали одновременно)
        self._semaphores = {p: asyncio.Semaphore(1) for p in Pattern}

        # Хранилище фоновых задач (отбиваемся от сборщика мусора)
        self.background_tasks: set[asyncio.Task] = set()

    def setup_routing(self) -> None:
        """Подписывается на системные события."""

        # Подключаем поллер к тикам
        self.bus.subscribe(Events.REACT_TICK_SAVED, self.poller.on_tick_saved)

        # Подписываем оркестратор на собственные триггеры
        self.bus.subscribe(Events.SUBCONSCIOUS_TRIGGERED, self._on_pattern_triggered)

    async def _on_pattern_triggered(self, **kwargs) -> None:
        """
        Ловит триггер от поллера и запускает Runner в фоне.
        """

        pattern = kwargs.get("pattern")
        if not pattern or not isinstance(pattern, Pattern):
            return

        # Запускаем как detached task (fire-and-forget), чтобы не блокировать EventBus
        task = asyncio.create_task(self._safe_run_pattern(pattern))
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def _safe_run_pattern(self, pattern: Pattern) -> None:
        """
        Обертка с семафором, чтобы предотвратить Database Locks от одновременного запуска.
        """

        if self._semaphores[pattern].locked():
            log = f"[Subconscious] Паттерн {pattern.value.upper()} уже выполняется, пропуск."
            subc_logger.debug(log)
            return

        async with self._semaphores[pattern]:
            try:
                limit = getattr(self.config.patterns, pattern.value).activation_limit_ticks
                await self.runner.run(pattern, ticks_to_analyze=limit)

            except Exception as e:
                log = f"[Subconscious] Критическая ошибка в паттерне {pattern.value.upper()}: {e}"
                subc_logger.error(log)
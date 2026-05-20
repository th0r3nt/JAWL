import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import (
    SubconsciousConfig,
    SubconsciousPatternsConfig,
    SubconsciousPatternConfig,
)

from src.l0_state.agent.state import AgentState
from src.l3_agent.subconscious.orchestrator import SubconsciousOrchestrator
from src.l3_agent.subconscious.schema import Pattern


@pytest.fixture
def integration_deps(tmp_path: Path):
    bus = EventBus()
    agent_state = AgentState()

    config = SubconsciousConfig(
        enabled=True,
        llm_model="test-model",
        patterns=SubconsciousPatternsConfig(
            consolidation=SubconsciousPatternConfig(enabled=True, activation_limit_ticks=2)
        ),
    )

    orchestrator = SubconsciousOrchestrator(
        config=config,
        executor=MagicMock(),
        sql_manager=MagicMock(),
        vector_manager=MagicMock(),
        graph_manager=MagicMock(),
        event_bus=bus,
        agent_state=agent_state,
        root_dir=tmp_path,
    )

    return bus, orchestrator, agent_state


@pytest.mark.asyncio
async def test_integration_eventbus_to_runner(integration_deps):
    """
    Интеграционный тест: EventBus -> Poller -> Orchestrator -> Runner.
    Проверяем, что публикация события `REACT_TICK_SAVED` реально доходит до
    Раннера с учетом лимитов (activation_limit_ticks = 2).
    """
    bus, orchestrator, agent_state = integration_deps

    # Включаем роутинг (Поллер слушает тики, Оркестратор слушает Поллер)
    orchestrator.setup_routing()

    # Мокаем сам Раннер, чтобы не дергать LLM в этом тесте
    orchestrator.runner.run = AsyncMock()

    # 1-й Тик
    await bus.publish(Events.REACT_TICK_SAVED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    # Лимит равен 2, поэтому Раннер еще не должен запуститься
    orchestrator.runner.run.assert_not_called()
    assert agent_state.subconscious_counters[Pattern.CONSOLIDATION.value]["current"] == 1

    # 2-й Тик
    await bus.publish(Events.REACT_TICK_SAVED)
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    # Ждем, пока Оркестратор отработает свою фоновую задачу (background_tasks)
    if orchestrator.background_tasks:
        await asyncio.gather(*orchestrator.background_tasks)

    # Проверяем, что Раннер был физически вызван
    orchestrator.runner.run.assert_awaited_once_with(Pattern.CONSOLIDATION, ticks_to_analyze=2)

    # Счетчик должен сброситься
    assert agent_state.subconscious_counters[Pattern.CONSOLIDATION.value]["current"] == 0

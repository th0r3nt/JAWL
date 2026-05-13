import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.utils.event.bus import EventBus
from src.utils.settings import (
    SubconsciousConfig,
    SubconsciousPatternsConfig,
    SubconsciousPatternConfig,
)
from src.utils.token_tracker import TokenTracker

from src.l0_state.agent.state import AgentState
from src.l1_databases.sql.db import SQLDB
from src.l1_databases.sql.management.ticks import SQLTicks

from src.l3_agent.subconscious.orchestrator import SubconsciousOrchestrator
from src.l3_agent.react.loop import ReactLoop
from src.l3_agent.skills.schema import ACTION_SCHEMA


@pytest.mark.asyncio
async def test_e2e_subconscious_full_pipeline(tmp_path: Path):
    """
    E2E Тест: Ядро -> EventBus -> Подсознание -> Вызов Навыка.
    Поднимаем реальный ReactLoop и In-Memory БД. Заставляем Главного агента сделать тик.
    Проверяем, что Подсознание просыпается и пытается выполнить команду.
    """

    # 1. РЕАЛЬНАЯ БАЗА (Для сохранения логов тиков)
    db = SQLDB(db_path=":memory:")
    db.engine = db.engine.execution_options(compiled_cache=None)
    db.engine.url = db.engine.url.set(database=":memory:")
    await db.connect()
    sql_ticks = SQLTicks(db=db)

    bus = EventBus()
    agent_state = AgentState(max_react_steps=1)

    # Лимит ставим в 1, чтобы подсознание сработало моментально
    config = SubconsciousConfig(
        enabled=True,
        llm_model="cheap-model",
        patterns=SubconsciousPatternsConfig(
            consolidation=SubconsciousPatternConfig(enabled=True, activation_limit_ticks=1)
        ),
    )

    # 2. МОКАЕМ LLM
    llm = MagicMock()
    mock_session = AsyncMock()

    # Ответ Главного агента (просто завершает цикл)
    mock_msg_react = MagicMock()
    mock_msg_react.content = '{"reflection": "Я завершаю цикл", "actions":[]}'
    mock_msg_react.tool_calls = None

    # Ответ Подсознания (Вызывает навык)
    mock_msg_subc = MagicMock()
    mock_msg_subc.content = '{"reflection": "Нашел факт", "actions": [{"tool_name": "mock.skill", "parameters": {}}]}'
    mock_msg_subc.tool_calls = None

    # Подсовываем ответы по очереди
    mock_session.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=mock_msg_react)]),
        MagicMock(choices=[MagicMock(message=mock_msg_subc)]),
    ]
    llm.get_session.return_value = mock_session

    # 3. ПОДСОЗНАНИЕ
    orchestrator = SubconsciousOrchestrator(
        config=config,
        llm_client=llm,
        sql_manager=MagicMock(),
        vector_manager=MagicMock(),
        graph_manager=MagicMock(),
        sql_ticks=sql_ticks,
        token_tracker=TokenTracker(),
        event_bus=bus,
        agent_state=agent_state,
        root_dir=tmp_path,
    )
    orchestrator.setup_routing()
    # Мокаем финальный вызов скилла, чтобы не дергать реальную функцию
    orchestrator.runner._execute_actions = AsyncMock()
    # Мокаем сборку контекста
    orchestrator.runner._build_dynamic_context = AsyncMock(return_value="Сырые дампы")

    # 4. ГЛАВНОЕ ЯДРО
    react = ReactLoop(
        llm_client=llm,
        prompt_builder=MagicMock(),
        context_builder=AsyncMock(),
        agent_state=agent_state,
        sql_ticks=sql_ticks,
        vector_manager=MagicMock(),
        token_tracker=TokenTracker(),
        tools=ACTION_SCHEMA,
        event_bus=bus,
    )
    react.context_builder.build.return_value = "Контекст главного агента"

    # ==========================
    # ЗАПУСК
    # ==========================

    await react.run("HEARTBEAT", {}, [])

    # Ждем, пока EventBus раскидает события
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    # Ждем, пока Подсознание завершит свою фоновую задачу
    if orchestrator.background_tasks:
        await asyncio.gather(*orchestrator.background_tasks)

    # ==========================
    # ПРОВЕРКИ
    # ==========================

    # Главный агент должен был сохранить свой тик
    ticks = await sql_ticks.get_ticks(1)
    assert len(ticks) == 1
    assert "завершаю цикл" in ticks[0].thoughts

    # Подсознание должно было запуститься, обратиться к LLM и вызвать скилл
    orchestrator.runner._execute_actions.assert_awaited_once()
    actions_called = orchestrator.runner._execute_actions.call_args[0][0]
    assert actions_called[0].tool_name == "mock.skill"

    await db.disconnect()

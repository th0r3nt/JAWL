import pytest
from pathlib import Path

from src.l0_state.agent.state import AgentState
from src.l1_databases.sql.manager import SQLManager
from src.l3_agent.context.registry import ContextRegistry, ContextSection
from src.l3_agent.context.builder import ContextBuilder


@pytest.mark.asyncio
async def test_integration_full_context_assembly():
    """
    Интеграционный тест: "Память -> Глаза".
    Поднимаем реальную in-memory SQLite, пишем туда задачу,
    собираем контекст через ContextBuilder и проверяем итоговый Markdown.
    """

    # 1. Инициализируем менеджер СРАЗУ с in-memory базой
    sql = SQLManager(db_path=Path(":memory:"))

    # Фикс для корректной работы in-memory sqlite в aiosqlite
    sql.db.engine = sql.db.engine.execution_options(compiled_cache=None)
    sql.db.engine.url = sql.db.engine.url.set(database=":memory:")

    # Коннект теперь успешно инициирует создание таблиц
    await sql.connect()

    # 3. Физически создаем задачу в БД
    await sql.tasks.create_task(
        title="Интеграционный тест БД",
        description="Проверка сборки Markdown",
        tags=["type:routine"],
    )

    # 4. Настраиваем реестр и сборщик
    registry = ContextRegistry()
    registry.register_provider("sql_tasks", sql.tasks.get_context_block, ContextSection.TASKS)

    agent_state = AgentState(llm_model="super-model-3000")

    # ИСПРАВЛЕНИЕ: Регистрируем сам AgentState (в main.py это делает SystemBuilder, а тут нужно вручную)
    registry.register_provider(
        "agent_state", agent_state.get_context_block, ContextSection.AGENT_STATE
    )

    builder = ContextBuilder(agent_state, registry)

    # 5. Собираем финальный промпт
    context_markdown = await builder.build(
        event_name="HEARTBEAT",
        payload={},
        missed_events=[
            {
                "name": "BACKGROUND_NOISE",
                "payload": {"msg": "Тишина"},
                "time": "12:00",
                "level": "LOW",
            }
        ],
    )

    # 6. Проверяем наличие всех кусков из разных подсистем
    assert "super-model-3000" in context_markdown  # Из AgentState
    assert "Интеграционный тест БД" in context_markdown  # Из SQL SQLite
    assert "type:routine" in context_markdown  # Из SQL SQLite
    assert "BACKGROUND_NOISE" in context_markdown  # Из missed_events
    assert "HEARTBEAT" in context_markdown  # Из главного триггера

    await sql.disconnect()

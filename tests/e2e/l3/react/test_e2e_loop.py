import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.l0_state.agent.state import AgentState
from src.l1_databases.sql.db import SQLDB
from src.l1_databases.sql.management.tasks import SQLTasks
from src.l1_databases.sql.management.ticks import SQLTicks

from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.registry import ContextRegistry, ContextSection
from src.l3_agent.context.builder import ContextBuilder
from src.utils.token_tracker import TokenTracker
from src.l3_agent.react.loop import ReactLoop
from src.l3_agent.skills.registry import register_instance, clear_registry
from src.l3_agent.skills.schema import ACTION_SCHEMA


@pytest.mark.asyncio
async def test_e2e_react_loop_creates_task_and_saves_tick(tmp_path: Path):
    """
    End-to-End тест ядра системы (ReAct).
    Проверяет весь жизненный цикл:
    1. Инициализация реальной БД (в RAM).
    2. Сборка реального контекста.
    3. Имитация ответа LLM (вызов SQLTasks.create_task).
    4. Проверка реального сохранения задачи в БД и логирования в Ticks.
    """

    # 1. Поднимаем РЕАЛЬНЫЕ БД (в памяти)
    db = SQLDB(db_path=":memory:")
    # Фикс для корректной работы in-memory sqlite в aiosqlite
    db.engine = db.engine.execution_options(compiled_cache=None)
    db.engine.url = db.engine.url.set(database=":memory:")

    await db.connect()

    sql_tasks = SQLTasks(db=db, max_tasks=5)
    sql_ticks = SQLTicks(db=db)

    # 2. Инициализируем реестр скиллов (очищаем от прошлых тестов и регистрируем реальный CRUD задач)
    clear_registry()
    register_instance(sql_tasks)

    # 3. Настраиваем реальный сборщик контекста
    agent_state = AgentState(max_react_steps=3)
    registry = ContextRegistry()
    registry.register_provider(
        "sql_tasks", sql_tasks.get_context_block, section=ContextSection.TASKS
    )
    context_builder = ContextBuilder(agent_state, registry)

    # 4. Создаем заглушки для того, что нам не нужно тестировать здесь
    prompt_builder = MagicMock(spec=PromptBuilder)
    prompt_builder.build.return_value = "System Prompt"

    vector_manager = MagicMock()
    token_tracker = TokenTracker()

    # 5. Имитируем ответ от LLM: Агент "подумал" и решил создать задачу
    llm_client = MagicMock()
    mock_session = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.tool_calls = None
    mock_msg.content = """
    {
      "thoughts": "Я получил запрос на создание теста. Занесу это в задачи.",
      "actions": [
        {
          "tool_name": "SQLTasks.create_task",
          "parameters": {
            "title": "E2E Интеграция",
            "description": "Проверить работу БД",
            "tags": ["type:routine"]
          }
        }
      ]
    }
    """
    mock_session.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=mock_msg)]
    )
    llm_client.get_session.return_value = mock_session

    # 6. Собираем петлю
    loop = ReactLoop(
        llm_client=llm_client,
        prompt_builder=prompt_builder,
        context_builder=context_builder,
        agent_state=agent_state,
        sql_ticks=sql_ticks,
        vector_manager=vector_manager,
        token_tracker=token_tracker,
        tools=ACTION_SCHEMA,
    )

    # ==============================
    # ⚡ ВЫПОЛНЕНИЕ
    # ==============================

    await loop.run(
        event_name="USER_MESSAGE",
        payload={"message": "Создай задачу на E2E тест"},
        missed_events=[],
    )

    # ==============================
    # 🎯 ПРОВЕРКИ (Ассерты)
    # ==============================

    # А. Проверяем, что задача РЕАЛЬНО создалась в базе
    task_context = await sql_tasks.get_context_block()
    assert "E2E Интеграция" in task_context
    assert "Проверить работу БД" in task_context
    assert "type:routine" in task_context

    # Б. Проверяем, что лог действий (Tick) РЕАЛЬНО записался в базу
    ticks = await sql_ticks.get_ticks(limit=5)
    assert len(ticks) >= 1
    last_tick = ticks[-1]

    # Проверяем мысли
    assert "занесу это в задачи" in last_tick.thoughts.lower()

    # Проверяем JSON действий
    assert len(last_tick.actions) == 1
    assert last_tick.actions[0]["tool_name"] == "SQLTasks.create_task"
    assert last_tick.actions[0]["parameters"]["title"] == "E2E Интеграция"

    # Проверяем, что результат успешный
    assert "создана" in last_tick.results.get("execution_report", "").lower()

    # Очищаем БД
    await db.disconnect()

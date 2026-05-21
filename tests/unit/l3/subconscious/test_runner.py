from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.l3_agent.subconscious.runner import SubconsciousRunner
from src.l3_agent.subconscious.schema import Pattern
from src.l3_agent.skills.schema import ActionCall


@pytest.fixture
def runner(mock_subconscious_deps):
    return SubconsciousRunner(
        executor=mock_subconscious_deps["executor"],
        model_name="cheap-model",
        sql_manager=mock_subconscious_deps["sql_manager"],
        vector_manager=mock_subconscious_deps["vector_manager"],
        graph_manager=mock_subconscious_deps["graph_manager"],
        root_dir=mock_subconscious_deps["root_dir"],
        max_steps=2,
    )


@pytest.mark.asyncio
async def test_runner_context_building(runner):
    """Тест: Маршрутизатор контекста собирает нужные дампы."""
    # Мокаем БД
    mock_tick = MagicMock(
        thoughts="Мысль 1", actions=[], created_at=datetime.now(timezone.utc)
    )
    runner.sql.ticks.get_ticks = AsyncMock(return_value=[mock_tick])
    runner.sql.ticks.tz_offset = 0  # <-- Жестко задаем число для часового пояса
    runner.sql.ticks.get_full_context_block = AsyncMock(return_value="Мысль 1")

    runner.vector.knowledge.get_all_knowledge = AsyncMock(
        return_value=MagicMock(message="Знания")
    )
    runner.vector.thoughts.get_all_thoughts = AsyncMock(
        return_value=MagicMock(message="Мысли")
    )

    # Заглушка для синхронного коннектора графа
    runner.graph.db.conn = MagicMock()
    mock_res = MagicMock()
    mock_res.has_next.side_effect = [True, False]
    mock_res.get_next.return_value = ["Узел", "Тип", "Опис"]
    runner.graph.db.conn.execute.return_value = mock_res

    # Тестируем Консолидацию (только тики)
    ctx_cons = await runner._build_dynamic_context(Pattern.CONSOLIDATION, 5)
    assert "Мысль 1" in ctx_cons
    assert "Знания" not in ctx_cons

    # Тестируем Забывание (тиков нет, есть знания/мысли/граф)
    ctx_forg = await runner._build_dynamic_context(Pattern.FORGETTING, 5)
    assert "Знания" in ctx_forg
    assert "Мысли" in ctx_forg
    assert "Узел" in ctx_forg


@pytest.mark.asyncio
@patch("src.l3_agent.subconscious.runner.call_skill", new_callable=AsyncMock)
@patch("src.l3_agent.subconscious.runner._REGISTRY")
async def test_runner_rbac_guard(mock_registry, mock_call_skill, runner):
    """Тест: Подсознание не может вызывать скиллы, которые ему не разрешены (RBAC)."""

    # Настраиваем реестр: навык разрешен только для REFLECTION
    mock_registry.get.return_value = {"subconscious": [Pattern.REFLECTION]}

    # Пытаемся вызвать этот навык из паттерна FORGETTING
    actions = [ActionCall(tool_name="Dangerous.skill", parameters={})]

    results = await runner._execute_actions(actions, Pattern.FORGETTING)

    assert "Access denied" in results
    assert "not allowed for the FORGETTING pattern" in results
    mock_call_skill.assert_not_called()


@pytest.mark.asyncio
async def test_runner_loop_termination(runner):
    """Тест: Цикл прерывается при emptyом массиве actions (штатное завершение)."""

    from unittest.mock import AsyncMock

    # Мокаем экзекутор, чтобы он вернул empty actions list действий
    runner.executor.execute = AsyncMock(
        return_value='{"reflection": "Я всё почистил", "actions":[]}'
    )

    # Заглушаем контекст
    runner._build_dynamic_context = AsyncMock(return_value="Контекст")
    runner._execute_actions = AsyncMock()

    await runner.run(Pattern.FORGETTING, 10)

    # LLM (executor) должна быть вызвана ровно 1 раз
    runner.executor.execute.assert_awaited_once()
    runner._execute_actions.assert_not_called()

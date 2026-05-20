import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.l3_agent.tot.schema import TreeResponse, ThoughtBranch
from src.l3_agent.tot.generator import ToTGenerator
from src.l0_state.agent.state import AgentState


def test_tot_schema_parsing():
    """Тест: Pydantic модель корректно парсит вложенный JSON, pros и cons теперь опциональны."""
    json_data = """
    {
        "branches": [
            {
                "name": "Стратегия 1",
                "description": "Делаем X",
                "pros": ["Быстро"],
                "cons": ["Опасно"],
                "sub_branches": [
                    {
                        "name": "Симуляция 1.1",
                        "description": "Если сервер упадет"
                    }
                ]
            },
            {
                "name": "Стратегия 2",
                "description": "Делаем Y"
            }
        ]
    }
    """

    parsed = TreeResponse.model_validate_json(json_data)
    assert len(parsed.branches) == 2
    assert parsed.branches[0].name == "Стратегия 1"
    assert parsed.branches[0].pros == ["Быстро"]

    assert len(parsed.branches[0].sub_branches) == 1
    assert parsed.branches[0].sub_branches[0].name == "Симуляция 1.1"
    # Проверяем, что отсутствующие поля заменились на пустые списки
    assert parsed.branches[0].sub_branches[0].pros == []
    assert parsed.branches[0].sub_branches[0].cons == []

    assert parsed.branches[1].name == "Стратегия 2"
    assert parsed.branches[1].cons == []


@pytest.mark.asyncio
async def test_tot_generator_rules_injection():
    """Тест: Генератор корректно вставляет динамические "мягкие" правила в промпт LLM."""
    mock_executor = AsyncMock()
    mock_executor.execute.return_value = '{"branches": []}'
    mock_executor.tracker = MagicMock()
    # Корректно мокаем реестр контекста, чтобы ._providers.keys() не падал
    mock_registry = MagicMock()
    mock_registry.gather_all = AsyncMock(return_value={})
    mock_registry._providers = {}

    mock_sql_ticks = MagicMock()
    mock_sql_ticks.get_full_context_block = AsyncMock(return_value="Fake Ticks")

    generator = ToTGenerator(
        executor=mock_executor,
        model_name="test",
        branches_count=4,  # 4 макро-ветки
        simulations_per_branch=3,  # 3 сценария на ветку
        max_depth=3,  # Глубина 3
        prompt_builder=MagicMock(),
        context_registry=mock_registry,
        agent_state=AgentState(),
        sql_ticks=mock_sql_ticks,
        root_dir=Path("."),
        timezone=3,
    )

    await generator.generate("TEST", {}, [], task_description="Особая задача")

    # Достаем отправленные сообщения
    call_args = mock_executor.execute.call_args[1]
    messages = call_args["messages"]
    user_prompt = messages[1]["content"]

    # Проверяем инъекцию новых "мягких" правил
    assert "Особая задача" in user_prompt
    assert "примерно ~4 макро-стратегий" in user_prompt
    assert "Рекомендованная глубина вложенности симуляции: ~3" in user_prompt
    assert "Ветви сценарии динамически: в среднем по 3" in user_prompt


def test_tot_generator_markdown_formatting():
    """Тест: Рекурсивный алгоритм корректно отрисовывает ASCII-дерево."""
    tree = TreeResponse(
        branches=[
            ThoughtBranch(
                name="План А",
                description="Делаем быстро",
                pros=["Скорость"],
                sub_branches=[ThoughtBranch(name="Осложнение", description="Всё сломалось")],
            ),
            ThoughtBranch(name="План Б", description="Делаем медленно"),
        ]
    )

    mock_sql_ticks = MagicMock()
    mock_sql_ticks.get_full_context_block = AsyncMock(return_value="Fake Ticks")

    generator = ToTGenerator(
        executor=MagicMock(),
        model_name="test",
        branches_count=2,
        simulations_per_branch=1,
        max_depth=2,
        prompt_builder=MagicMock(),
        context_registry=MagicMock(),
        agent_state=AgentState(),
        sql_ticks=mock_sql_ticks,
        root_dir=Path("."),
        timezone=3,
    )

    result = generator._format_markdown(tree)

    # Проверяем структуру дерева
    assert '├── №1: "План А" -> Делаем быстро' in result
    assert "│   * Плюсы: [+] Скорость" in result
    assert "│   └── №1.1: Осложнение -> Всё сломалось" in result
    assert "│\n│" in result  # Проверяем пустую разделительную линию
    assert '└── №2: "План Б" -> Делаем медленно' in result


@pytest.mark.asyncio
async def test_tot_generator_call_llm_success():
    """Тест: Генератор успешно вызывает LLMExecutor и парсит JSON-ответ."""
    mock_executor = AsyncMock()
    # Имитируем успешный возврат валидного JSON дерева
    mock_executor.execute.return_value = (
        '{"branches": [{"name": "Plan", "description": "Desc"}]}'
    )
    mock_executor.tracker = MagicMock()

    mock_sql_ticks = MagicMock()
    mock_sql_ticks.get_full_context_block = AsyncMock(return_value="Fake Ticks")

    # Корректно мокаем реестр контекста, чтобы ._providers.keys() не падал
    mock_registry = MagicMock()
    mock_registry.gather_all = AsyncMock(return_value={})
    mock_registry._providers = {}

    mock_sql_ticks = MagicMock()
    mock_sql_ticks.get_full_context_block = AsyncMock(return_value="Fake Ticks")

    generator = ToTGenerator(
        executor=mock_executor,
        model_name="test",
        branches_count=3,
        simulations_per_branch=2,
        max_depth=2,
        prompt_builder=MagicMock(),
        context_registry=mock_registry,
        agent_state=AgentState(),
        sql_ticks=mock_sql_ticks,
        root_dir=Path("."),
        timezone=3,
    )

    res = await generator.generate("TEST", {}, [])

    # Проверяем, что парсер сработал и вернул отформатированный Markdown
    assert res is not None
    assert "TREE OF THOUGHTS" in res
    assert "Plan" in res
    mock_executor.execute.assert_awaited_once()

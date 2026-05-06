import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.l3_agent.tot.schema import TreeResponse, ThoughtBranch
from src.l3_agent.tot.generator import ToTGenerator
from src.l0_state.agent.state import AgentState


def test_tot_schema_parsing():
    """Тест: Pydantic модель корректно парсит вложенный JSON (фрактал) от LLM."""
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
                        "description": "Если сервер упадет",
                        "pros": [],
                        "cons": ["Downtime"]
                    }
                ]
            },
            {
                "name": "Стратегия 2",
                "description": "Делаем Y",
                "pros": ["Безопасно"],
                "cons": []
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
    assert parsed.branches[0].sub_branches[0].cons == ["Downtime"]


@pytest.mark.asyncio
async def test_tot_generator_rules_injection():
    """Тест: Генератор корректно вставляет динамические правила геометрии в промпт LLM."""
    mock_llm = MagicMock()
    mock_session = AsyncMock()

    # Заглушка ответа модели
    mock_msg = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.function.arguments = '{"branches": []}'
    mock_msg.tool_calls = [mock_tool_call]

    mock_session.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=mock_msg)]
    )
    mock_llm.get_session.return_value = mock_session

    # Корректно мокаем реестр контекста, чтобы ._providers.keys() не падал
    mock_registry = MagicMock()
    mock_registry.gather_all = AsyncMock(return_value={})
    mock_registry._providers = {}

    generator = ToTGenerator(
        llm_client=mock_llm,
        model_name="test",
        branches_count=4,  # 4 макро-ветки
        simulations_per_branch=3,  # 3 сценария на ветку
        max_depth=3,  # Глубина 3
        prompt_builder=MagicMock(),
        context_registry=mock_registry,
        agent_state=AgentState(),
        token_tracker=MagicMock(),
        root_dir=Path("."),
        timezone=3,
    )

    await generator.generate("TEST", {}, [], task_description="Особая задача")

    # Достаем отправленные сообщения
    call_args = mock_session.chat.completions.create.call_args[1]
    messages = call_args["messages"]
    user_prompt = messages[1]["content"]

    # Проверяем инъекцию бетона
    assert "Особая задача" in user_prompt
    assert "ровно 4 макро-стратегий" in user_prompt
    assert "глубина вложенности симуляции: 3" in user_prompt


@pytest.mark.asyncio
async def test_tot_generator_call_llm_success():
    """Тест: Генератор успешно вызывает LLM и достает аргументы из tool_calls."""
    mock_llm = MagicMock()
    mock_session = AsyncMock()

    mock_msg = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.function.arguments = '{"branches": []}'
    mock_msg.tool_calls = [mock_tool_call]

    mock_session.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=mock_msg)]
    )
    mock_llm.get_session.return_value = mock_session

    generator = ToTGenerator(
        llm_client=mock_llm,
        model_name="test",
        branches_count=3,
        simulations_per_branch=2,
        max_depth=2,
        prompt_builder=MagicMock(),
        context_registry=MagicMock(),
        agent_state=AgentState(),
        token_tracker=MagicMock(),
        root_dir=Path("."),
        timezone=3,
    )

    res = await generator._call_llm([{"role": "user", "content": "test"}])
    assert res == '{"branches": []}'

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.l3_agent.tot.schema import TreeResponse, ThoughtBranch
from src.l3_agent.tot.generator import ToTGenerator
from src.l0_state.agent.state import AgentState


def test_tot_schema_parsing():
    """Тест: Pydantic модель корректно парсит валидный JSON от LLM."""
    json_data = """
    {
        "branches": [
            {
                "name": "Ветка 1",
                "description": "Сделать X",
                "estimated_speed": "Быстро",
                "complexity": "Низкая",
                "risk_assessment": "Минимальный"
            },
            {
                "name": "Ветка 2",
                "description": "Сделать Y"
            }
        ]
    }
    """
    parsed = TreeResponse.model_validate_json(json_data)
    assert len(parsed.branches) == 2
    assert parsed.branches[0].name == "Ветка 1"
    assert parsed.branches[0].estimated_speed == "Быстро"
    assert parsed.branches[1].estimated_speed is None  # Опциональное поле


@pytest.mark.asyncio
async def test_tot_generator_format_markdown():
    """Тест: Генератор корректно превращает объект в Markdown-строку для промпта."""
    generator = ToTGenerator(
        llm_client=MagicMock(),
        model_name="test",
        branches_count=3,
        prompt_builder=MagicMock(),
        context_registry=MagicMock(),
        agent_state=AgentState(),
        token_tracker=MagicMock(),
        root_dir=Path("."),
        timezone=3,
    )

    tree = TreeResponse(
        branches=[
            ThoughtBranch(
                name="Стратегия А",
                description="Анализ логов",
                risk_assessment="Безопасно",
            )
        ]
    )

    md = generator._format_markdown(tree)
    assert "## TREE OF THOUGHTS" in md
    assert "Время генерации: Шаг" in md
    assert "**Ветка: Стратегия А**" in md
    assert "*Описание:* Анализ логов" in md
    assert "*Риски:* Безопасно" in md
    assert "*Сложность:*" not in md  # Не должно быть, так как None


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
        prompt_builder=MagicMock(),
        context_registry=MagicMock(),
        agent_state=AgentState(),
        token_tracker=MagicMock(),
        root_dir=Path("."),
        timezone=3,
    )

    res = await generator._call_llm([{"role": "user", "content": "test"}])
    assert res == '{"branches": []}'

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l3_agent.tot.skills import DeepThinkSkill
from src.l0_state.agent.state import AgentState


@pytest.mark.asyncio
async def test_deep_think_skill_success():
    """Тест: Навык deep_think делает запрос в генератор, передает фокус и обновляет стейт."""
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(return_value="## TREE OF THOUGHTS\nВетка...")
    mock_generator.agent_state = AgentState()

    skill = DeepThinkSkill(mock_generator)
    res = await skill.deep_think(task_description="Придумай как взломать пентагон")

    assert res.is_success is True
    assert "successfully simulated" in res.message

    # Проверяем, что кэш агента обновился
    assert "Ветка..." in mock_generator.agent_state.current_thoughts_tree

    # Проверяем, что фокус-задача ушла в генератор
    call_kwargs = mock_generator.generate.call_args[1]
    assert call_kwargs["task_description"] == "Придумай как взломать пентагон"


@pytest.mark.asyncio
async def test_deep_think_skill_fail():
    """Тест: Навык deep_think обрабатывает ошибку генерации."""
    mock_generator = MagicMock()
    mock_generator.generate = AsyncMock(return_value=None)
    mock_generator.agent_state = AgentState()

    skill = DeepThinkSkill(mock_generator)
    res = await skill.deep_think()

    assert res.is_success is False
    assert "Failed to generate" in res.message
    assert mock_generator.agent_state.current_thoughts_tree == ""

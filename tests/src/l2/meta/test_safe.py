import pytest
from src.l2_interfaces.meta.skills.level_safe import MetaSafe


@pytest.mark.asyncio
async def test_meta_change_model(meta_client):
    """Тест навыка: смена модели LLM."""
    skills = MetaSafe(meta_client)
    res = await skills.change_model("claude-opus-4.7")

    assert res.is_success is True
    assert meta_client.agent_state.llm_model == "claude-opus-4.7"


@pytest.mark.asyncio
async def test_meta_change_temperature(meta_client):
    """Тест навыка: смена температуры LLM."""
    skills = MetaSafe(meta_client)
    res = await skills.change_temperature(0.9)

    assert res.is_success is True
    assert meta_client.agent_state.temperature == 0.9

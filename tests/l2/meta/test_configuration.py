import pytest
from src.utils.event.registry import Events
from src.l2_interfaces.meta.skills.configuration import MetaConfiguration


@pytest.mark.asyncio
async def test_meta_change_model(meta_client):
    """Тест навыка: смена модели LLM."""
    skills = MetaConfiguration(meta_client)
    res = await skills.change_model("test-model-v2")

    assert res.is_success is True
    assert meta_client.agent_state.llm_model == "test-model-v2"


@pytest.mark.asyncio
async def test_meta_change_temperature(meta_client):
    """Тест навыка: смена температуры LLM."""
    skills = MetaConfiguration(meta_client)
    res = await skills.change_temperature(0.9)

    assert res.is_success is True
    assert meta_client.agent_state.temperature == 0.9


@pytest.mark.asyncio
async def test_meta_change_heartbeat_interval(meta_client):
    """Тест навыка: изменение пульса с пробросом события в EventBus."""
    skills = MetaConfiguration(meta_client)
    res = await skills.change_heartbeat_interval(120)

    assert res.is_success is True

    meta_client.bus.publish.assert_called_once()
    call_args = meta_client.bus.publish.call_args

    assert call_args[0][0] == Events.SYSTEM_CONFIG_UPDATED
    assert call_args[1]["key"] == "heartbeat_interval"
    assert call_args[1]["value"] == 120

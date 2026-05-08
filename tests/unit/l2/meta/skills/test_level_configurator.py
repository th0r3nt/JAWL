import pytest
from src.utils.event.registry import Events
from src.l2_interfaces.meta.skills.level_configurator import MetaConfigurator


@pytest.fixture
def config_skills(meta_client, tmp_path):
    return MetaConfigurator(meta_client, root_dir=tmp_path)


@pytest.mark.asyncio
async def test_change_heartbeat_interval(config_skills, meta_client):
    res = await config_skills.change_heartbeat_interval(120)

    assert res.is_success is True
    assert meta_client.agent_state.heartbeat_interval == 120
    meta_client.bus.publish.assert_called_with(
        Events.SYSTEM_CONFIG_UPDATED, key="heartbeat_interval", value=120
    )


@pytest.mark.asyncio
async def test_change_max_react_steps(config_skills, meta_client):
    res = await config_skills.change_max_react_steps(20)

    assert res.is_success is True
    assert meta_client.agent_state.max_react_steps == 20


@pytest.mark.asyncio
async def test_change_database_limits(config_skills, meta_client):
    res = await config_skills.change_database_limits("mental_states", 50)

    assert res.is_success is True
    meta_client.bus.publish.assert_called_with(
        Events.SYSTEM_CONFIG_UPDATED, key="db_limit", module="mental_states", value=50
    )


@pytest.mark.asyncio
async def test_change_context_depth(config_skills, meta_client):
    res = await config_skills.change_context_depth(high_ticks=5, medium_ticks=10, low_ticks=20)

    assert res.is_success is True
    assert meta_client.agent_state.context_high_ticks == 5
    assert meta_client.agent_state.context_medium_ticks == 10
    assert meta_client.agent_state.context_low_ticks == 20

    meta_client.bus.publish.assert_called_with(
        Events.SYSTEM_CONFIG_UPDATED,
        key="context_depth",
        high_ticks=5,
        medium_ticks=10,
        low_ticks=20,
    )

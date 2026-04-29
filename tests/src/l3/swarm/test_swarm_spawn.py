import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.l3_agent.swarm.spawn import SwarmManager
from src.utils.settings import SwarmConfig
from src.l3_agent.swarm.roles import Subagents


@pytest.fixture
def mock_registry():
    # Мокаем глобальный реестр, используя РЕАЛЬНЫЕ объекты ролей
    return {
        "HostOSFiles.read_file": {"swarm_roles": [Subagents.CODER]},
        "HostOSExecution.execute_script": {"swarm_roles": [Subagents.CODER]},
        "DeepResearch.deep_research": {"swarm_roles": [Subagents.WEB_RESEARCHER]},
    }


@pytest.fixture
def swarm_manager(mock_registry):
    config = SwarmConfig(enabled=True, subagent_model="cheap-model", max_concurrent_workers=2)
    mock_llm = MagicMock()
    mock_tracker = MagicMock()

    with patch("src.l3_agent.swarm.spawn._REGISTRY", mock_registry):
        with patch("src.l3_agent.swarm.spawn.SwarmPromptBuilder"):
            return SwarmManager(mock_llm, config, MagicMock(), mock_tracker)


@pytest.mark.asyncio
async def test_spawn_disabled(swarm_manager):
    swarm_manager.config.enabled = False
    res = await swarm_manager.spawn_subagent("coder", "Task")
    assert res.is_success is False
    assert "отключена" in res.message


@pytest.mark.asyncio
async def test_spawn_unknown_model(swarm_manager):
    swarm_manager.config.subagent_model = "unknown"
    res = await swarm_manager.spawn_subagent("coder", "Task")
    assert res.is_success is False
    assert "не указана модель" in res.message


@pytest.mark.asyncio
async def test_spawn_unknown_role(swarm_manager):
    res = await swarm_manager.spawn_subagent("hacker", "Task")
    assert res.is_success is False
    assert "недоступна" in res.message


@pytest.mark.asyncio
@patch("src.l3_agent.swarm.spawn.SubagentLoop")
async def test_spawn_success_background_task(mock_loop_class, swarm_manager):
    mock_loop_instance = MagicMock()
    mock_loop_instance.run = AsyncMock()
    mock_loop_class.return_value = mock_loop_instance

    res = await swarm_manager.spawn_subagent("coder", "Fix bugs")

    assert res.is_success is True
    assert "успешно запущен" in res.message

    assert len(swarm_manager.active_tasks) == 1

    for task in list(swarm_manager.active_tasks):
        await task

    mock_loop_instance.run.assert_awaited_once()


def test_swarm_manager_dynamic_docstring(mock_registry):
    config = SwarmConfig(enabled=True, subagent_model="model")

    # Сценарий 1: Роли активны
    with patch("src.l3_agent.swarm.spawn._REGISTRY", mock_registry):
        manager1 = SwarmManager(MagicMock(), config, MagicMock(), MagicMock())
        assert "coder" in manager1.spawn_subagent.__doc__
        assert "web_researcher" in manager1.spawn_subagent.__doc__

    # Сценарий 2: Host OS выключен (нету скиллов для coder)
    empty_registry = {
        "DeepResearch.deep_research": {"swarm_roles": [Subagents.WEB_RESEARCHER]}
    }
    with patch("src.l3_agent.swarm.spawn._REGISTRY", empty_registry):
        manager2 = SwarmManager(MagicMock(), config, MagicMock(), MagicMock())
        assert "coder" not in manager2.spawn_subagent.__doc__
        assert "web_researcher" in manager2.spawn_subagent.__doc__

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l2_interfaces.meta.client import MetaClient
from src.l2_interfaces.meta.skills.configuration import MetaConfiguration
from src.l2_interfaces.meta.skills.system import MetaSystem


@pytest.fixture
def temp_settings_file(tmp_path: Path) -> Path:
    settings_file = tmp_path / "settings.yaml"
    data = """
identity:
  agent_name: AgentEpta
llm:
  model_name: claude-opus-4.7
  temperature: 0.7
  max_react_steps: 15
system:
  heartbeat_interval: 60
    """
    settings_file.write_text(data.strip(), encoding="utf-8")
    return settings_file


@pytest.fixture
def meta_client(temp_settings_file):    
    """Инициализирует MetaClient с моками шины и стейта."""
    
    agent_state = AgentState()
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()

    return MetaClient(agent_state=agent_state, event_bus=bus, settings_path=temp_settings_file)


@pytest.mark.asyncio
async def test_meta_client_update_setting(meta_client, temp_settings_file):
    """Тест: MetaClient должен физически перезаписывать yaml файл."""

    success = await meta_client.update_setting(
        path_keys=["llm", "model_name"], new_value="new-fast-model"
    )

    assert success is True

    content = temp_settings_file.read_text(encoding="utf-8")
    assert "new-fast-model" in content
    assert "claude-opus-4.7" not in content


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


@pytest.mark.asyncio
async def test_meta_off_system(meta_client):
    """Тест навыка: запрос на выключение системы."""
    skills = MetaSystem(meta_client)
    res = await skills.off_system(reason="Test shutdown")

    assert res.is_success is True
    meta_client.bus.publish.assert_called_once()
    call_args = meta_client.bus.publish.call_args
    assert call_args[0][0] == Events.SYSTEM_SHUTDOWN_REQUESTED


@pytest.mark.asyncio
async def test_meta_reboot_system(meta_client):
    """Тест навыка: запрос на перезагрузку системы."""

    skills = MetaSystem(meta_client)
    res = await skills.reboot_system(reason="Test reboot")
    assert res.is_success is True
    meta_client.bus.publish.assert_called_once()
    call_args = meta_client.bus.publish.call_args
    assert call_args[0][0] == Events.SYSTEM_REBOOT_REQUESTED
    assert call_args[1]["reason"] == "Test reboot"

import pytest
from src.utils.event.registry import Events
from src.l2_interfaces.meta.skills.system import MetaSystem


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

import pytest
from src.utils.event.registry import Events
from src.l2_interfaces.meta.skills.system import MetaSystem


@pytest.mark.asyncio
async def test_meta_system_off(meta_client):
    """Тест: команда выключения через MetaSystem."""
    skills = MetaSystem(meta_client)

    res = await skills.off_system(reason="tired")

    assert res.is_success is True
    meta_client.bus.publish.assert_called_with(
        Events.SYSTEM_SHUTDOWN_REQUESTED, reason="tired"
    )


@pytest.mark.asyncio
async def test_meta_system_reboot(meta_client):
    """Тест: команда перезагрузки через MetaSystem."""
    skills = MetaSystem(meta_client)

    res = await skills.reboot_system(reason="update")

    assert res.is_success is True
    meta_client.bus.publish.assert_called_with(Events.SYSTEM_REBOOT_REQUESTED, reason="update")

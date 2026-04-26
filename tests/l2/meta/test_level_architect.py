import pytest
from src.utils.event.registry import Events
from src.l2_interfaces.meta.skills.level_architect import MetaArchitect


@pytest.mark.asyncio
async def test_toggle_interface_success(meta_client):
    """Тест: Включение интерфейса меняет YAML."""
    skills = MetaArchitect(meta_client)

    res = await skills.toggle_interface("host_os", True)

    assert res.is_success is True
    content = meta_client.interfaces_path.read_text(encoding="utf-8")
    assert "enabled: true" in content


@pytest.mark.asyncio
async def test_toggle_interface_no_keys_fail(meta_client):
    """Тест: Telegram не включится, если в .env нет ключей."""
    skills = MetaArchitect(meta_client)

    # Мокаем проверку ключей (типа в .env ничего нет)
    meta_client.has_env_key = lambda k: False

    res = await skills.toggle_interface("telegram_kurigram", True)
    assert res.is_success is False
    assert "TELETHON_API_ID" in res.message


@pytest.mark.asyncio
async def test_off_system(meta_client):
    """Тест: команда выключения пробрасывается в EventBus."""
    skills = MetaArchitect(meta_client)

    res = await skills.off_system(reason="Going to sleep")

    assert res.is_success is True
    meta_client.bus.publish.assert_called_with(
        Events.SYSTEM_SHUTDOWN_REQUESTED, reason="Going to sleep"
    )


@pytest.mark.asyncio
async def test_reboot_system(meta_client):
    """Тест: команда ребута пробрасывается в EventBus."""
    skills = MetaArchitect(meta_client)

    res = await skills.reboot_system(reason="Update limits")

    assert res.is_success is True
    meta_client.bus.publish.assert_called_with(
        Events.SYSTEM_REBOOT_REQUESTED, reason="Update limits"
    )

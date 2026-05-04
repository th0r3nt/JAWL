import pytest
from unittest.mock import MagicMock

from src.utils.event.registry import Events

from src.l2_interfaces.meta.skills.level_creator import MetaCreator


@pytest.fixture
def creator_skills(meta_client):
    mock_registry = MagicMock()
    return MetaCreator(meta_client, registry=mock_registry)


@pytest.mark.asyncio
async def test_creator_register_custom_skill(creator_skills):
    creator_skills.registry.register_skill.return_value = (True, "Custom.my_func")

    res = await creator_skills.register_custom_skill(
        "my_func", "desc", "file.py", "func", {"arg": "str"}
    )

    assert res.is_success is True
    assert "Custom.my_func" in res.message
    creator_skills.registry.register_skill.assert_called_once()


@pytest.mark.asyncio
async def test_creator_remove_custom_skill(creator_skills):
    creator_skills.registry.unregister_skill.return_value = (True, "")

    res = await creator_skills.remove_custom_skill("Custom.my_func")

    assert res.is_success is True
    creator_skills.registry.unregister_skill.assert_called_once_with("Custom.my_func")


@pytest.mark.asyncio
async def test_creator_set_dashboard_block(creator_skills, meta_client):
    """Тест: Навык set_dashboard_block публикует событие создания/обновления."""
    res = await creator_skills.set_dashboard_block("Metrics", "CPU: 10%")

    assert res.is_success is True
    meta_client.bus.publish.assert_called_once_with(
        Events.SYSTEM_DASHBOARD_UPDATE, name="Metrics", content="CPU: 10%"
    )


@pytest.mark.asyncio
async def test_creator_remove_dashboard_block(creator_skills, meta_client):
    """Тест: Навык remove_dashboard_block публикует событие с пустым контентом (удаление)."""
    res = await creator_skills.remove_dashboard_block("Metrics")

    assert res.is_success is True
    meta_client.bus.publish.assert_called_once_with(
        Events.SYSTEM_DASHBOARD_UPDATE, name="Metrics", content=""
    )

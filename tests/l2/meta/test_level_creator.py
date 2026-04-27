import pytest
from unittest.mock import MagicMock
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

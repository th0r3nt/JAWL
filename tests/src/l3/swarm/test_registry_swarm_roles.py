import pytest
from src.l3_agent.skills.registry import skill, _REGISTRY, clear_registry
from src.l3_agent.swarm.roles import Subagents


@pytest.fixture(autouse=True)
def clean_reg():
    original = _REGISTRY.copy()
    clear_registry()
    yield
    _REGISTRY.clear()
    _REGISTRY.update(original)


def test_skill_decorator_stores_swarm_roles():
    """Тест: декоратор @skill корректно сохраняет объекты ролей в глобальный реестр."""

    @skill(swarm_roles=[Subagents.CODER, Subagents.WEB_RESEARCHER])
    def my_cool_func():
        pass

    assert len(_REGISTRY) == 1

    # Достаем то имя, под которым навык реально сохранился
    skill_name = list(_REGISTRY.keys())[0]
    skill_data = _REGISTRY[skill_name]

    assert "my_cool_func" in skill_name
    assert len(skill_data["swarm_roles"]) == 2
    assert Subagents.CODER in skill_data["swarm_roles"]
    assert Subagents.WEB_RESEARCHER in skill_data["swarm_roles"]

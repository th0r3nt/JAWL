from src.l3_agent.swarm.roles import Subagents, SubagentRole


def test_subagents_all():
    """Тест: метод all() собирает все классовые атрибуты типа SubagentRole."""
    roles = Subagents.all()

    assert len(roles) >= 2
    assert all(isinstance(r, SubagentRole) for r in roles)

    ids = [r.id for r in roles]
    assert "coder" in ids
    assert "web_researcher" in ids


def test_subagents_get_by_id():
    """Тест: метод get_by_id() корректно находит роли по строковому ID."""
    coder = Subagents.get_by_id("coder")
    assert coder is not None
    assert coder.name == "Software Engineer"

    # Несуществующая роль
    unknown = Subagents.get_by_id("hacker_1337")
    assert unknown is None

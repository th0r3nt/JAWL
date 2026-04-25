import pytest
from src.l3_agent.skills import registry
from src.l3_agent.skills.schema import ActionCall
from src.l3_agent.skills.registry import (
    skill,
    register_instance,
    execute_skill,
    SkillResult,
    get_skills_library,
)

# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture(autouse=True)
def clean_registry():
    original_registry = registry._REGISTRY.copy()
    original_docs = registry._SKILL_DOCS.copy()

    registry._REGISTRY.clear()
    registry._SKILL_DOCS.clear()

    yield

    # Возвращаем всё как было
    registry._REGISTRY.clear()
    registry._SKILL_DOCS.clear()
    registry._REGISTRY.update(original_registry)
    registry._SKILL_DOCS.extend(original_docs)


class DummyInterface:
    def __init__(self, prefix: str):
        self.prefix = prefix

    @skill(name_override="mock.class_func")
    async def dummy_class_func(self, text: str) -> SkillResult:
        """Метод класса для теста."""
        return SkillResult.ok(f"{self.prefix}: {text}")

    @skill(name_override="mock.fail_func")
    async def failing_func(self) -> SkillResult:
        return SkillResult.fail("Упс, ошибка")

    async def not_a_skill(self):
        pass


@pytest.fixture
def mock_plain_func():
    """Регистрируем обычную функцию после того, как clean_registry очистит кэш."""

    @skill(name_override="mock.plain_func")
    async def dummy_plain_func(text: str) -> SkillResult:
        return SkillResult.ok(f"Plain: {text}")

    return dummy_plain_func


# ===================================================================
# TESTS
# ===================================================================


@pytest.mark.asyncio
async def test_plain_function_registration(mock_plain_func):
    assert "mock.plain_func" in registry._REGISTRY
    docs = get_skills_library()
    assert "mock.plain_func" in docs


@pytest.mark.asyncio
async def test_execute_skill_success(mock_plain_func):
    dummy = DummyInterface(prefix="Agent")
    register_instance(dummy)

    actions = [
        ActionCall(tool_name="mock.plain_func", parameters={"text": "Hello"}),
        ActionCall(tool_name="mock.class_func", parameters={"text": "World"}),
    ]

    report = await execute_skill(actions=actions)

    assert "Action [mock.plain_func]: Plain: Hello" in report
    assert "Action [mock.class_func]: Agent: World" in report


@pytest.mark.asyncio
async def test_execute_skill_ignores_extra_kwargs(mock_plain_func):
    actions = [
        ActionCall(
            tool_name="mock.plain_func", parameters={"text": "Valid", "hallucination": 123}
        )
    ]
    report = await execute_skill(actions=actions)
    assert "Action [mock.plain_func]: Plain: Valid" in report


@pytest.mark.asyncio
async def test_execute_skill_mixed_results(mock_plain_func):
    """Тест: оркестратор должен переварить смесь валидных, падающих и несуществующих скиллов."""

    @skill(name_override="mock.fail_func")
    async def fail_func():
        raise RuntimeError("Критический сбой")

    actions = [
        ActionCall(tool_name="mock.plain_func", parameters={"text": "A"}),
        ActionCall(tool_name="mock.unknown_func", parameters={}),
        ActionCall(tool_name="mock.fail_func", parameters={}),
    ]

    report = await execute_skill(actions)

    assert "Action [mock.plain_func]: Plain: A" in report
    assert "Action [mock.unknown_func]: Скилл 'mock.unknown_func' не найден" in report
    assert "Action [mock.fail_func]: Ошибка: Критический сбой" in report

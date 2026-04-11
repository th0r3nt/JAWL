import pytest
from src.l3_agent.skills import registry
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
    """
    Фикстура, которая автоматически очищает глобальный реестр скиллов
    перед каждым тестом, чтобы тесты не пересекались.
    """
    # Сохраняем оригинальное состояние (вдруг что-то из main.py уже загрузилось)
    original_registry = registry._REGISTRY.copy()
    original_docs = registry._SKILL_DOCS.copy()

    registry._REGISTRY.clear()
    registry._SKILL_DOCS.clear()

    yield  # Выполняется тест

    # Возвращаем всё как было
    registry._REGISTRY.clear()
    registry._SKILL_DOCS.clear()
    registry._REGISTRY.update(original_registry)
    registry._SKILL_DOCS.extend(original_docs)


# ===================================================================
# MOCKS
# ===================================================================

# Обычную функцию убрали отсюда, перенесли в фикстуру ниже.


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
        """Эта функция не должна попасть в реестр"""
        pass


@pytest.fixture
def mock_plain_func():
    """Регистрируем обычную функцию после того, как clean_registry очистит кэш."""

    @skill(name_override="mock.plain_func")
    async def dummy_plain_func(text: str) -> SkillResult:
        """Обычная функция для теста."""
        return SkillResult.ok(f"Plain: {text}")

    return dummy_plain_func


# ===================================================================
# TESTS
# ===================================================================


@pytest.mark.asyncio
async def test_plain_function_registration(mock_plain_func):
    """Тест: обычная функция сразу попадает в реестр."""
    assert "mock.plain_func" in registry._REGISTRY
    docs = get_skills_library()
    assert "mock.plain_func" in docs
    assert "Обычная функция для теста." in docs


@pytest.mark.asyncio
async def test_execute_skill_success(mock_plain_func):
    """Тест: успешный вызов нескольких скиллов параллельно."""
    dummy = DummyInterface(prefix="Agent")
    register_instance(dummy)

    actions = [
        {"tool_name": "mock.plain_func", "parameters": {"text": "Hello"}},
        {"tool_name": "mock.class_func", "parameters": {"text": "World"}},
    ]

    report = await execute_skill(thoughts="Проверка", actions=actions)

    assert "Action [mock.plain_func]: OK - Plain: Hello" in report
    assert "Action [mock.class_func]: OK - Agent: World" in report


@pytest.mark.asyncio
async def test_execute_skill_ignores_extra_kwargs(mock_plain_func):
    """
    Тест: если LLM сгаллюцинирует и передаст лишние аргументы,
    система должна их отфильтровать, а не крашить функцию.
    """
    actions = [
        {"tool_name": "mock.plain_func", "parameters": {"text": "Valid", "hallucination": 123}}
    ]

    report = await execute_skill(thoughts="Лишние данные", actions=actions)

    # Функция должна успешно отработать, проигнорировав "hallucination"
    assert "Action [mock.plain_func]: OK - Plain: Valid" in report

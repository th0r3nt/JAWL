import pytest
import inspect
from pathlib import Path
from src.l3_agent.skills.custom import CustomSkillsRegistry
from src.l3_agent.skills import registry


@pytest.fixture
def custom_registry(tmp_path: Path):
    return CustomSkillsRegistry(data_dir=tmp_path)


def test_custom_registry_register_and_unregister(custom_registry):
    """Тест: успешная регистрация и удаление кастомного скилла."""

    # 1. Регистрация
    success, name = custom_registry.register_skill(
        skill_name="test_skill",
        description="Тестовый навык",
        filepath="sandbox/test.py",
        func_name="do_test",
        params={"arg1": "str"},
    )

    assert success is True
    assert name == "Custom.test_skill"
    assert "Custom.test_skill" in registry._REGISTRY

    # Проверяем метапрограммирование сигнатуры
    func = registry._REGISTRY["Custom.test_skill"]["func"]
    
    sig = inspect.signature(func)
    assert "arg1" in sig.parameters

    # Проверяем документацию
    assert any("Custom.test_skill" in doc for doc in registry._CUSTOM_SKILL_DOCS)
    assert any("Тестовый навык" in doc for doc in registry._CUSTOM_SKILL_DOCS)

    # 2. Удаление
    success_del, _ = custom_registry.unregister_skill("Custom.test_skill")
    assert success_del is True
    assert "Custom.test_skill" not in registry._REGISTRY
    assert not any("Custom.test_skill" in doc for doc in registry._CUSTOM_SKILL_DOCS)


def test_custom_registry_load_persistence(custom_registry):
    """Тест: реестр восстанавливает навыки из JSON файла."""
    custom_registry.register_skill("persist_skill", "Desc", "file.py", "func", {})

    # Очищаем глобальный кэш
    registry.clear_registry()
    assert "Custom.persist_skill" not in registry._REGISTRY

    # Имитируем перезапуск агента
    custom_registry.load_and_register_all()

    assert "Custom.persist_skill" in registry._REGISTRY

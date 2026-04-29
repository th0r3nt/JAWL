import pytest
from src.l3_agent.skills.registry import (
    skill,
    register_instance,
    get_skills_library,
    clear_registry,
    _REGISTRY,
)
from src.l2_interfaces.host.os.decorators import require_access
from src.l2_interfaces.host.os.client import HostOSAccessLevel


class MockHostOS:
    def __init__(self, level):
        self.access_level = level


class DummyDangerousInterface:
    def __init__(self, host_os):
        self.host_os = host_os

    @skill()
    @require_access(HostOSAccessLevel.OPERATOR)
    async def rm_rf_root(self):
        """Dangerous stuff."""
        return None

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def read_safe_file(self):
        """Safe stuff."""
        return None


@pytest.fixture(autouse=True)
def clean():
    # Сохраняем состояние глобального реестра до теста
    original = _REGISTRY.copy()
    clear_registry()

    yield

    # После теста очищаем мусор и возвращаем всё как было (используем original)
    clear_registry()
    _REGISTRY.update(original)


def test_skill_visibility_based_on_access_level():
    """Тест: get_skills_library скрывает скиллы, если access_level агента ниже требуемого."""

    # 1. Агент в песочнице (SANDBOX = 0)
    mock_os_sandbox = MockHostOS(HostOSAccessLevel.SANDBOX)
    interface_sandbox = DummyDangerousInterface(mock_os_sandbox)
    register_instance(interface_sandbox)

    docs_sandbox = get_skills_library()

    # Он должен видеть безопасный скилл, но НЕ должен видеть опасный
    assert "read_safe_file" in docs_sandbox
    assert "rm_rf_root" not in docs_sandbox  # Скрыто!

    # 2. Повышаем права до OPERATOR (2)
    clear_registry()
    mock_os_operator = MockHostOS(HostOSAccessLevel.OPERATOR)
    interface_operator = DummyDangerousInterface(mock_os_operator)
    register_instance(interface_operator)

    docs_operator = get_skills_library()

    # Теперь он должен видеть оба скилла
    assert "read_safe_file" in docs_operator
    assert "rm_rf_root" in docs_operator  # Появилось!

import pytest
from unittest.mock import patch
from src.l2_interfaces.host.os.client import HostOSAccessLevel
from src.l2_interfaces.host.os.skills.execution import HostOSExecution

from src.l2_interfaces.host.os.decorators import require_access
from src.l3_agent.skills.registry import SkillResult


class DummyOSClass:
    def __init__(self, host_os_client):
        self.host_os = host_os_client

    @require_access(HostOSAccessLevel.OPERATOR)
    async def dangerous_action(self):
        return SkillResult.ok("Бум! Я удалил базу!")


@pytest.mark.asyncio
async def test_execute_shell_command_safe(os_client):
    """Тест: выполнение простой безопасной кроссплатформенной команды."""
    os_client.access_level = HostOSAccessLevel.ROOT  # Требуется для shell_command
    executor = HostOSExecution(os_client)

    # Используем python -c, так как это работает везде (Windows, Linux, Mac)
    res = await executor.execute_shell_command("python -c \"print('Agent Online')\"")

    assert res.is_success is True
    assert "Agent Online" in res.message
    assert "Команда завершилась с кодом 0" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.execution.psutil.Process")
async def test_execution_kill_process_not_found(mock_process, os_client):
    """Тест: Агент пытается убить процесс, которого не существует."""
    import psutil

    os_client.access_level = HostOSAccessLevel.ROOT
    executor = HostOSExecution(os_client)

    mock_process.side_effect = psutil.NoSuchProcess(pid=99999)

    res = await executor.kill_process(pid=99999)
    assert res.is_success is False
    assert "не найден" in res.message


@pytest.mark.asyncio
async def test_require_access_decorator_blocks(os_client):
    """Тест: Декоратор блокирует выполнение, если Access Level ниже требуемого."""
    # os_client из фикстуры имеет уровень OBSERVER (1)
    dummy = DummyOSClass(os_client)

    res = await dummy.dangerous_action()

    # Действие требует OPERATOR (2), поэтому должно быть заблокировано
    assert res.is_success is False
    assert "Отказано в доступе" in res.message
    assert "1 (OBSERVER)" in res.message


@pytest.mark.asyncio
async def test_require_os_access_decorator_allows(os_client):
    """Тест: Декоратор пропускает выполнение, если Access Level достаточный."""
    # Повышаем права до ROOT (3)
    os_client.access_level = HostOSAccessLevel.ROOT
    dummy = DummyOSClass(os_client)

    res = await dummy.dangerous_action()

    # Должно отработать
    assert res.is_success is True
    assert "Бум" in res.message

import pytest
from unittest.mock import patch
from src.l2_interfaces.host.os.client import HostOSAccessLevel
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.skills.system import HostOSSystem


@pytest.mark.asyncio
async def test_execute_shell_command_safe(os_client):
    """Тест: выполнение простой безопасной кроссплатформенной команды."""
    os_client.access_level = HostOSAccessLevel.OPERATOR  # Требуется для shell_command
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

    os_client.access_level = HostOSAccessLevel.OPERATOR
    executor = HostOSExecution(os_client)

    mock_process.side_effect = psutil.NoSuchProcess(pid=99999)

    res = await executor.kill_process(pid=99999)
    assert res.is_success is False
    assert "не найден" in res.message


@pytest.mark.asyncio
async def test_get_telemetry(os_client):
    """Тест: получение телеметрии ОС."""
    sys_skill = HostOSSystem(os_client)
    res = await sys_skill.get_telemetry()

    assert res.is_success is True
    assert "CPU" in res.message
    assert "RAM" in res.message
    assert "Uptime" in res.message

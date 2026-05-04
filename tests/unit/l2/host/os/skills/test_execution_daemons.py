import pytest
from unittest.mock import patch, MagicMock
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.client import HostOSAccessLevel


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.execution.subprocess.Popen")
async def test_start_daemon_success(mock_popen, os_client):
    """Тест: запуск фонового скрипта (демона) и регистрация в реестре."""
    os_client.access_level = HostOSAccessLevel.OPERATOR
    executor = HostOSExecution(os_client)
    
    script_path = os_client.sandbox_dir / "worker.py"
    script_path.touch()
    
    mock_process = MagicMock()
    mock_process.pid = 9999
    mock_popen.return_value = mock_process
    
    res = await executor.start_daemon("sandbox/worker.py", "BackgroundWorker", "Test description")
    
    assert res.is_success is True
    assert "PID: 9999" in res.message
    
    # Проверяем реестр
    registry = os_client.get_daemons_registry()
    assert "9999" in registry
    assert registry["9999"]["name"] == "BackgroundWorker"
    assert registry["9999"]["filepath"] == "worker.py"


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.execution.psutil.Process")
async def test_stop_daemon_success(mock_process_cls, os_client):
    """Тест: остановка демона по PID и удаление из реестра."""
    os_client.access_level = HostOSAccessLevel.OPERATOR
    executor = HostOSExecution(os_client)
    
    # Подготавливаем реестр
    registry = {"8888": {"name": "OldWorker", "filepath": "worker.py"}}
    os_client.set_daemons_registry(registry)
    
    mock_proc = MagicMock()
    mock_process_cls.return_value = mock_proc
    
    res = await executor.stop_daemon(8888)
    
    assert res.is_success is True
    assert "успешно остановлен" in res.message
    
    mock_proc.terminate.assert_called_once()
    
    # Убеждаемся, что демон вычищен из реестра
    updated_registry = os_client.get_daemons_registry()
    assert "8888" not in updated_registry
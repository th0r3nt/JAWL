import pytest
from unittest.mock import patch, MagicMock
from src.l2_interfaces.host.os.skills.system import HostOSSystem


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.system.psutil.process_iter")
async def test_list_top_processes_access_denied(mock_process_iter, os_client):
    """Тест: обработка процессов с запрещенным доступом (AccessDenied)."""
    import psutil

    sys_skill = HostOSSystem(os_client)

    # Имитируем два процесса: один читается нормально, другой бросает AccessDenied
    mock_good_proc = MagicMock()
    mock_good_proc.info = {"pid": 1, "name": "systemd", "memory_percent": 5.0}

    mock_bad_proc = MagicMock()

    # process_iter возвращает объекты, у которых мы запрашиваем .info
    # Для bad_proc делаем так, чтобы обращение к .info бросало AccessDenied
    type(mock_bad_proc).info = PropertyMock(side_effect=psutil.AccessDenied())

    mock_process_iter.return_value = [mock_good_proc, mock_bad_proc]

    res = await sys_skill.list_top_processes()

    assert res.is_success is True
    assert "systemd" in res.message
    assert "PID: `1`" in res.message


@pytest.mark.asyncio
async def test_get_uptime(os_client):
    """Тест: аптайм возвращается корректно."""
    sys_skill = HostOSSystem(os_client)
    res = await sys_skill.get_uptime()
    assert res.is_success is True
    assert ":" in res.message  # Проверка формата 00:00:00


@pytest.mark.asyncio
async def test_get_datetime(os_client):
    """Тест: время возвращается корректно."""
    sys_skill = HostOSSystem(os_client)
    res = await sys_skill.get_datetime()
    assert res.is_success is True
    assert "-" in res.message and ":" in res.message


# Вспомогательный класс для мока свойства
class PropertyMock(MagicMock):
    def __get__(self, obj, obj_type=None):
        return self()

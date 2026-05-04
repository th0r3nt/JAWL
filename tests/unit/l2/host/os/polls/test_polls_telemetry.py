import pytest
from unittest.mock import patch
from src.l2_interfaces.host.os.polls.telemetry import TelemetryPoller


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.polls.telemetry.psutil")
@patch("src.l2_interfaces.host.os.polls.telemetry.socket.create_connection")
async def test_telemetry_poller_updates_state(mock_socket, mock_psutil, os_client):
    """Тест: поллер корректно обновляет L0 стейт метриками."""
    poller = TelemetryPoller(os_client, os_client.state)

    # Мокаем системные вызовы
    mock_psutil.cpu_percent.return_value = 15.5
    mock_mem = mock_psutil.virtual_memory.return_value
    mock_mem.percent = 40.0
    mock_mem.total = 16 * 1024**3
    mock_mem.available = 8 * 1024**3
    mock_psutil.boot_time.return_value = 0

    mock_psutil.process_iter.return_value = []

    # Мокаем успешный интернет
    mock_socket.return_value.__enter__.return_value = True

    # Дергаем методы вручную (без запуска цикла)
    poller._update_datetime_and_uptime()
    poller._update_telemetry()
    await poller._update_network()

    # Проверяем стейт
    assert "15.5%" in os_client.state.telemetry
    assert "40.0%" in os_client.state.telemetry
    assert "Online" in os_client.state.network


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.polls.telemetry.socket.create_connection")
async def test_telemetry_poller_offline(mock_socket, os_client):
    """Тест: поллер корректно определяет отсутствие интернета."""
    poller = TelemetryPoller(os_client, os_client.state)

    # Имитируем отсутствие сети
    mock_socket.side_effect = OSError("Network unreachable")

    await poller._update_network()

    assert "Offline" in os_client.state.network

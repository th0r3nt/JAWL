import pytest
from src.l2_interfaces.host.os.skills.network import HostOSNetwork


@pytest.mark.asyncio
async def test_ping_localhost(os_client):
    """Тест: успешный пинг локалхоста."""
    net = HostOSNetwork(os_client)
    res = await net.ping_host("127.0.0.1", count=1)

    assert res.is_success is True
    assert "is reachable" in res.message


@pytest.mark.asyncio
async def test_check_closed_port(os_client):
    """Тест: проверка заведомо closedого порта должна корректно возвращать Fail без краша."""
    net = HostOSNetwork(os_client)
    # Используем случайный порт, который вряд ли открыт
    res = await net.check_port("127.0.0.1", 54321, timeout=1)

    assert res.is_success is False
    # Либо таймаут, либо ConnectionRefused
    assert "Connection refused" in res.message or "Timeout" in res.message

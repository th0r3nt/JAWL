import pytest
from unittest.mock import MagicMock, patch
from src.l2_interfaces.host.os.skills.network import HostOSNetwork


@pytest.mark.asyncio
async def test_ping_localhost(os_client):
    """Тест: успешный пинг локалхоста."""
    net = HostOSNetwork(os_client)
    res = await net.ping_host("127.0.0.1", count=1)

    assert res.is_success is True
    assert "доступен" in res.message


@pytest.mark.asyncio
async def test_check_closed_port(os_client):
    """Тест: проверка заведомо закрытого порта должна корректно возвращать Fail без краша."""
    net = HostOSNetwork(os_client)
    # Используем случайный порт, который вряд ли открыт
    res = await net.check_port("127.0.0.1", 54321, timeout=1)

    assert res.is_success is False
    # Либо таймаут, либо ConnectionRefused
    assert "отказано" in res.message or "Таймаут" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.network.urllib.request.urlopen")
async def test_network_http_request_truncation(mock_urlopen, os_client):
    """Тест: Ответ от HTTP-запроса обрезается, если он слишком большой."""
    network = HostOSNetwork(os_client)
    os_client.config.http_response_max_chars = 100

    # Имитируем гигантский ответ
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"A" * 500  # 500 байт
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    res = await network.http_request("http://fake.url")

    assert res.is_success is True
    assert "Статус: 200" in res.message
    # Проверяем, что сработал лимит в 100 символов
    assert "Превышен лимит символов" in res.message
    assert len(res.message) < 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "FILE:///etc/shadow",
        "ftp://internal.example/secret",
        "data:text/plain,leak",
        "javascript:alert(1)",
        "/etc/passwd",
        "",
    ],
)
@patch("src.l2_interfaces.host.os.skills.network.urllib.request.urlopen")
async def test_http_request_blocks_non_http_schemes(mock_urlopen, os_client, url):
    """Гард: http_request не должен открывать ничего кроме http(s)."""
    network = HostOSNetwork(os_client)
    res = await network.http_request(url)

    assert res.is_success is False
    assert "Запрещённая схема" in res.message
    mock_urlopen.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/shadow",
        "ftp://internal.example/secret",
        "data:text/plain,leak",
    ],
)
@patch("src.l2_interfaces.host.os.skills.network.urllib.request.urlopen")
async def test_download_file_blocks_non_http_schemes(mock_urlopen, os_client, url):
    """Гард: download_file не должен скачивать через file:// и прочие нестандартные схемы."""
    network = HostOSNetwork(os_client)
    res = await network.download_file(url, "leak.txt")

    assert res.is_success is False
    assert "Запрещённая схема" in res.message
    mock_urlopen.assert_not_called()

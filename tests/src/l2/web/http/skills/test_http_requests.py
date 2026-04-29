import pytest
from unittest.mock import MagicMock, patch
from src.l2_interfaces.web.http.skills.requests import WebHTTPRequests


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.http.skills.requests.urllib.request.urlopen")
async def test_network_http_request_truncation(mock_urlopen, http_client):
    """Тест: Ответ от HTTP-запроса обрезается, если он слишком большой."""
    skills = WebHTTPRequests(http_client)

    # Имитируем гигантский ответ (500 байт при лимите в 100)
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"A" * 500
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    res = await skills.http_request("http://fake.url")

    assert res.is_success is True
    assert "Статус: 200" in res.message
    # Проверяем, что сработал лимит в 100 символов (установленный в фикстуре)
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
@patch("src.l2_interfaces.web.http.skills.requests.urllib.request.urlopen")
async def test_http_request_blocks_non_http_schemes(mock_urlopen, http_client, url):
    """Гард: http_request не должен открывать ничего кроме http(s)."""
    skills = WebHTTPRequests(http_client)
    res = await skills.http_request(url)

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
@patch("src.l2_interfaces.web.http.skills.requests.urllib.request.urlopen")
async def test_download_file_blocks_non_http_schemes(mock_urlopen, http_client, url):
    """Гард: download_file не должен скачивать через file:// и прочие нестандартные схемы."""
    skills = WebHTTPRequests(http_client)
    res = await skills.download_file(url, "leak.txt")

    assert res.is_success is False
    assert "Запрещённая схема" in res.message
    mock_urlopen.assert_not_called()

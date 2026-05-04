import pytest
from unittest.mock import patch, MagicMock
import urllib.error


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.jina_read.urllib.request.urlopen")
async def test_jina_read_success(mock_urlopen, jina_skill):
    """Тест: успешное чтение через r.jina.ai."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"Clean Markdown Content from Jina"
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    res = await jina_skill.read_webpage("https://example.com")

    assert res.is_success is True
    assert "Clean Markdown Content from Jina" in res.message
    assert "Jina" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.jina_read.urllib.request.urlopen")
async def test_jina_read_http_error(mock_urlopen, jina_skill):
    """Тест: Jina ловит 404/403 HTTP ошибку."""
    mock_urlopen.side_effect = urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    res = await jina_skill.read_webpage("https://example.com")

    assert res.is_success is False
    assert "Ошибка HTTP" in res.message
    assert "404 Not Found" in res.message

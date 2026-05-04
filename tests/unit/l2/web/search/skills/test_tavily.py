import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.tavily_search.urllib.request.urlopen")
async def test_tavily_search_success(mock_urlopen, tavily_skill):
    """Тест: успешный поиск через Tavily API."""

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "results": [
                {
                    "title": "Tavily Title",
                    "url": "https://tavily.com",
                    "content": "Tavily Snippet",
                }
            ]
        }
    ).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    res = await tavily_skill.search("AI news", max_results=1)

    assert res.is_success is True
    assert "Tavily Title" in res.message
    assert "https://tavily.com" in res.message
    assert "Tavily Snippet" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.tavily_search.urllib.request.urlopen")
async def test_tavily_search_exception(mock_urlopen, tavily_skill):
    """Тест: обработка ошибки от API Tavily."""
    mock_urlopen.side_effect = Exception("API Key Invalid")

    res = await tavily_skill.search("test")

    assert res.is_success is False
    assert "API Key Invalid" in res.message

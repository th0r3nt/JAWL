import pytest
from unittest.mock import patch


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.trafilatura_read.trafilatura")
async def test_read_webpage_success(mock_trafilatura, trafilatura_skill):
    """Тест: успешный парсинг веб-страницы через Trafilatura."""
    mock_trafilatura.fetch_url.return_value = "<html><body>Some text</body></html>"
    mock_trafilatura.extract.return_value = "Parsed Text Content"

    res = await trafilatura_skill.read_webpage("https://example.com")

    assert res.is_success is True
    assert "Parsed Text Content" in res.message
    mock_trafilatura.fetch_url.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.trafilatura_read.trafilatura")
async def test_read_webpage_truncation(mock_trafilatura, trafilatura_skill):
    """Тест: обрезка слишком длинной страницы под лимит клиента."""
    long_text = "A" * 200
    mock_trafilatura.fetch_url.return_value = "<html></html>"
    mock_trafilatura.extract.return_value = long_text

    res = await trafilatura_skill.read_webpage("https://example.com")

    assert res.is_success is True
    assert len(res.message) < 300
    assert "Текст обрезан" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.trafilatura_read.trafilatura")
async def test_read_webpage_fetch_fail(mock_trafilatura, trafilatura_skill):
    """Тест: обработка ошибки скачивания (404, 403)."""
    mock_trafilatura.fetch_url.return_value = None

    res = await trafilatura_skill.read_webpage("https://example.com")

    assert res.is_success is False
    assert "не удалось прочитать" in res.message

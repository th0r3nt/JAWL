import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.duckduckgo_search.DDGS")
async def test_web_search_success(mock_ddgs_class, ddg_skill):
    """Тест: успешный поиск в интернете."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {"title": "Test Title", "href": "https://test.com", "body": "Test Snippet"}
    ]
    mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs_instance

    res = await ddg_skill.search("test query", max_results=1)

    assert res.is_success is True
    assert "Test Title" in res.message
    assert "https://test.com" in res.message
    assert "Test Snippet" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.duckduckgo_search.DDGS")
async def test_web_search_empty(mock_ddgs_class, ddg_skill):
    """Тест: обработка пустого результата поиска."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = []
    mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs_instance

    res = await ddg_skill.search("test query")

    assert res.is_success is True
    assert "ничего не найдено" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.duckduckgo_search.asyncio.sleep") # Мокаем сон
@patch("src.l2_interfaces.web.search.skills.duckduckgo_search.DDGS")
async def test_web_search_exception(mock_ddgs_class, mock_sleep, ddg_skill):
    """Тест: перехват сетевой ошибки (без ожидания ретраев)."""
    # Имитируем падение DDGS
    mock_ddgs_class.side_effect = Exception("Connection Reset")

    res = await ddg_skill.search("test query")

    assert res.is_success is False
    assert "Ошибка веб-поиска" in res.message
    assert "Connection Reset" in res.message
    
    # Проверяем, что ретраи реально были (sleep вызывался 3 раза)
    assert mock_sleep.call_count == 3
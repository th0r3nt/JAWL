import pytest
from unittest.mock import patch, MagicMock

from src.l2_interfaces.web.search.client import WebClient
from src.l0_state.interfaces.state import WebSearchState
from src.l2_interfaces.web.search.skills.duckduckgo import DuckDuckGoSearch
from src.l2_interfaces.web.search.skills.webpages import WebPages


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def web_client():
    return WebClient(state=WebSearchState(), request_timeout=5, max_page_chars=100)


@pytest.fixture
def search_skill(web_client):
    return DuckDuckGoSearch(client=web_client)


@pytest.fixture
def pages_skill(web_client):
    return WebPages(client=web_client)


# ===================================================================
# TESTS: CLIENT
# ===================================================================


def test_web_client_init():
    """Тест: корректная инициализация клиента с параметрами."""
    client = WebClient(state=WebSearchState(), request_timeout=10, max_page_chars=500)
    assert client.timeout == 10
    assert client.max_page_chars == 500


# ===================================================================
# TESTS: SEARCH
# ===================================================================


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.duckduckgo.DDGS")
async def test_web_search_success(mock_ddgs_class, search_skill):
    """Тест: успешный поиск в интернете."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {"title": "Test Title", "href": "https://test.com", "body": "Test Snippet"}
    ]
    # Настраиваем контекстный менеджер (with DDGS() as ddgs:)
    mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs_instance

    res = await search_skill.web_search("test query", max_results=1)

    assert res.is_success is True
    assert "Test Title" in res.message
    assert "https://test.com" in res.message
    assert "Test Snippet" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.duckduckgo.DDGS")
async def test_web_search_empty(mock_ddgs_class, search_skill):
    """Тест: обработка пустого результата поиска."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = []
    mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs_instance

    res = await search_skill.web_search("test query")

    assert res.is_success is True
    assert "ничего не найдено" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.duckduckgo.DDGS")
async def test_web_search_exception(mock_ddgs_class, search_skill):
    """Тест: перехват сетевой ошибки (например, таймаут DDGS)."""
    mock_ddgs_class.side_effect = Exception("Connection Reset")

    res = await search_skill.web_search("test query")

    assert res.is_success is False
    assert "Ошибка веб-поиска" in res.message
    assert "Connection Reset" in res.message


# ===================================================================
# TESTS: WEBPAGES
# ===================================================================


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.webpages.trafilatura")
async def test_read_webpage_success(mock_trafilatura, pages_skill):
    """Тест: успешное чтение и парсинг страницы."""
    mock_trafilatura.fetch_url.return_value = "<html><body>Some text</body></html>"
    mock_trafilatura.extract.return_value = "Parsed Text Content"

    res = await pages_skill.read_webpage("https://example.com")

    assert res.is_success is True
    assert res.message == "Parsed Text Content"
    mock_trafilatura.fetch_url.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.webpages.trafilatura")
async def test_read_webpage_truncation(mock_trafilatura, pages_skill):
    """Тест: обрезка слишком длинной страницы под лимит клиента."""
    long_text = "A" * 200
    mock_trafilatura.fetch_url.return_value = "<html></html>"
    mock_trafilatura.extract.return_value = long_text

    # В фикстуре max_page_chars установлен на 100
    res = await pages_skill.read_webpage("https://example.com")

    assert res.is_success is True
    assert len(res.message) < 200
    assert "Текст обрезан" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.search.skills.webpages.trafilatura")
async def test_read_webpage_fetch_fail(mock_trafilatura, pages_skill):
    """Тест: обработка ошибки скачивания (404, 403, etc)."""
    mock_trafilatura.fetch_url.return_value = None

    res = await pages_skill.read_webpage("https://example.com")

    assert res.is_success is False
    assert "не удалось прочитать" in res.message
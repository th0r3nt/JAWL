import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.l2_interfaces.web.client import WebClient
from src.l0_state.interfaces.state import WebState
from src.l2_interfaces.web.skills.search import WebSearch
from src.l2_interfaces.web.skills.webpages import WebPages
from src.l2_interfaces.web.skills.research import WebResearch


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def web_client():
    return WebClient(state=WebState(), request_timeout=5, max_page_chars=100)


@pytest.fixture
def search_skill(web_client):
    return WebSearch(client=web_client)


@pytest.fixture
def pages_skill(web_client):
    return WebPages(client=web_client)


@pytest.fixture
def research_skill(web_client, search_skill, pages_skill):
    return WebResearch(client=web_client, search_skill=search_skill, pages_skill=pages_skill)


# ===================================================================
# TESTS: CLIENT
# ===================================================================


def test_web_client_init():
    """Тест: корректная инициализация клиента с параметрами."""
    client = WebClient(state=WebState(), request_timeout=10, max_page_chars=500)
    assert client.timeout == 10
    assert client.max_page_chars == 500


# ===================================================================
# TESTS: SEARCH
# ===================================================================


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.skills.search.DDGS")
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
@patch("src.l2_interfaces.web.skills.search.DDGS")
async def test_web_search_empty(mock_ddgs_class, search_skill):
    """Тест: обработка пустого результата поиска."""
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = []
    mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs_instance

    res = await search_skill.web_search("test query")

    assert res.is_success is True
    assert "ничего не найдено" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.skills.search.DDGS")
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
@patch("src.l2_interfaces.web.skills.webpages.trafilatura")
async def test_read_webpage_success(mock_trafilatura, pages_skill):
    """Тест: успешное чтение и парсинг страницы."""
    mock_trafilatura.fetch_url.return_value = "<html><body>Some text</body></html>"
    mock_trafilatura.extract.return_value = "Parsed Text Content"

    res = await pages_skill.read_webpage("https://example.com")

    assert res.is_success is True
    assert res.message == "Parsed Text Content"
    mock_trafilatura.fetch_url.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
@patch("src.l2_interfaces.web.skills.webpages.trafilatura")
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
@patch("src.l2_interfaces.web.skills.webpages.trafilatura")
async def test_read_webpage_fetch_fail(mock_trafilatura, pages_skill):
    """Тест: обработка ошибки скачивания (404, 403, etc)."""
    mock_trafilatura.fetch_url.return_value = None

    res = await pages_skill.read_webpage("https://example.com")

    assert res.is_success is False
    assert "не удалось прочитать" in res.message


# ===================================================================
# TESTS: RESEARCH
# ===================================================================


@pytest.mark.asyncio
async def test_deep_research_success(research_skill, search_skill, pages_skill):
    """Тест: успешный конвейер поиска, дедупликации и чтения."""

    # Мокаем сырые методы, чтобы не триггерить реальные библиотеки
    search_skill.search_raw = AsyncMock(
        side_effect=[
            [{"href": "url1", "title": "T1"}, {"href": "url2", "title": "T2"}],
            [
                {"href": "url2", "title": "T2"},
                {"href": "url3", "title": "T3"},
            ],  # Дубликат url2
        ]
    )
    pages_skill.read_raw = AsyncMock(side_effect=["Content 1", "Content 2", "Content 3"])

    res = await research_skill.deep_research(["query1", "query2"])

    assert res.is_success is True
    assert "### T1\nURL: url1\nContent 1" in res.message
    assert "### T2\nURL: url2\nContent 2" in res.message
    assert "### T3\nURL: url3\nContent 3" in res.message

    # Проверка, что сырой поиск вызывался дважды (по количеству запросов)
    assert search_skill.search_raw.call_count == 2
    # Проверка, что сырое чтение вызывалось 3 раза (дубликат url2 был отсеян)
    assert pages_skill.read_raw.call_count == 3


@pytest.mark.asyncio
async def test_deep_research_empty_queries(research_skill):
    """Тест: обработка пустого массива запросов."""
    res = await research_skill.deep_research([])
    assert res.is_success is False
    assert "Список запросов пуст" in res.message


@pytest.mark.asyncio
async def test_deep_research_no_links_found(research_skill, search_skill):
    """Тест: поиск ничего не вернул."""
    search_skill.search_raw = AsyncMock(return_value=[])

    res = await research_skill.deep_research(["query1"])

    assert res.is_success is False
    assert "Не найдено ни одной ссылки" in res.message


@pytest.mark.asyncio
async def test_deep_research_partial_failures(research_skill, search_skill, pages_skill):
    """Тест: оркестратор должен выживать, если часть страниц упала при чтении."""
    search_skill.search_raw = AsyncMock(
        return_value=[{"href": "url1", "title": "T1"}, {"href": "bad_url", "title": "Bad"}]
    )

    # Одна страница прочиталась, вторая выбросила исключение (таймаут)
    pages_skill.read_raw = AsyncMock(side_effect=["Good Content", Exception("Timeout")])

    res = await research_skill.deep_research(["query"])

    assert res.is_success is True
    assert "Good Content" in res.message
    assert "[Ошибка чтения / Блокировка]" in res.message

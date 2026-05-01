import pytest
from src.l2_interfaces.web.search.client import WebSearchClient
from src.l0_state.interfaces.web.search_state import WebSearchState
from src.l2_interfaces.web.search.skills.duckduckgo_search import DuckDuckGoSearch
from src.l2_interfaces.web.search.skills.tavily_search import TavilySearch
from src.l2_interfaces.web.search.skills.trafilatura_read import TrafilaturaReader
from src.l2_interfaces.web.search.skills.jina_read import JinaReader


@pytest.fixture
def web_client():
    return WebSearchClient(state=WebSearchState(), request_timeout=5, max_page_chars=100)


@pytest.fixture
def ddg_skill(web_client):
    return DuckDuckGoSearch(client=web_client)


@pytest.fixture
def tavily_skill(web_client):
    return TavilySearch(client=web_client, api_key="fake_key_123")


@pytest.fixture
def trafilatura_skill(web_client):
    return TrafilaturaReader(client=web_client)


@pytest.fixture
def jina_skill(web_client):
    return JinaReader(client=web_client)

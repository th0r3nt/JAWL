import pytest
from src.l2_interfaces.web.search.client import WebSearchClient
from src.l0_state.interfaces.state import WebSearchState
from src.l2_interfaces.web.search.skills.duckduckgo import DuckDuckGoSearch
from src.l2_interfaces.web.search.skills.webpages import WebPages


@pytest.fixture
def web_client():
    return WebSearchClient(state=WebSearchState(), request_timeout=5, max_page_chars=100)


@pytest.fixture
def search_skill(web_client):
    return DuckDuckGoSearch(client=web_client)


@pytest.fixture
def pages_skill(web_client):
    return WebPages(client=web_client)

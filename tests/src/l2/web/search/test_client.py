from src.l2_interfaces.web.search.client import WebSearchClient
from src.l2_interfaces.web.search.state import WebSearchState


def test_web_search_client_init():
    """Тест: корректная инициализация клиента с параметрами."""
    client = WebSearchClient(state=WebSearchState(), request_timeout=10, max_page_chars=500)
    assert client.timeout == 10
    assert client.max_page_chars == 500

import pytest
from src.utils.settings import WebHTTPConfig
from src.l2_interfaces.web.http.state import WebHTTPState
from src.l2_interfaces.web.http.client import WebHTTPClient


@pytest.fixture
def http_client():
    config = WebHTTPConfig(
        enabled=True,
        request_timeout_sec=10,
        max_response_chars=100,  # Маленький лимит специально для тестов обрезки
    )
    state = WebHTTPState(history_limit=5)
    return WebHTTPClient(state=state, config=config)

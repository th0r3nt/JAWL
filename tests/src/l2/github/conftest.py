import pytest
from unittest.mock import AsyncMock
from src.l0_state.interfaces.state import GithubState
from src.utils.settings import GithubConfig
from src.l2_interfaces.github.client import GithubClient


@pytest.fixture
def github_config():
    return GithubConfig(
        enabled=True, agent_account=True, request_timeout_sec=10, history_limit=5
    )


@pytest.fixture
def github_state():
    return GithubState(history_limit=5)


@pytest.fixture
def mock_github_client(github_state, github_config):
    """Клиент с замоканным методом request, чтобы не дергать сеть в тестах скиллов."""
    client = GithubClient(state=github_state, config=github_config, token="fake_token")
    client.request = AsyncMock()
    return client

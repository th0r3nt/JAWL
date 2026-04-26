import pytest
from unittest.mock import MagicMock
from unittest.mock import call
from src.l2_interfaces.github.skills.watchers import GithubWatchers


@pytest.fixture
def watchers_skill(mock_github_client):
    mock_events = MagicMock()
    return GithubWatchers(mock_github_client, mock_events)


@pytest.mark.asyncio
async def test_track_repository_success(watchers_skill, mock_github_client):
    """Тест: успешное добавление репозитория в отслеживаемые."""
    res = await watchers_skill.track_repository("th0r3nt", "JAWL")

    assert res.is_success is True
    assert "th0r3nt/JAWL" in watchers_skill.client.state.tracked_repos
    watchers_skill.events.save_persisted_repos.assert_called_once()

    # Если в фикстуре мока включен agent_account и есть токен, то вызывается и GET, и PUT
    if watchers_skill.client.config.agent_account and watchers_skill.client.token:
        mock_github_client.request.assert_has_calls([
            call("GET", "/repos/th0r3nt/JAWL"),
            call("PUT", "/repos/th0r3nt/JAWL/subscription", body={'subscribed': True})
        ], any_order=False)
    else:
        mock_github_client.request.assert_called_once_with("GET", "/repos/th0r3nt/JAWL")


@pytest.mark.asyncio
async def test_untrack_repository_success(watchers_skill, mock_github_client):
    """Тест: успешное удаление репозитория из отслеживаемых."""
    # Подготавливаем стейт
    watchers_skill.client.state.tracked_repos["th0r3nt/JAWL"] = "12345"
    
    res = await watchers_skill.untrack_repository("th0r3nt", "JAWL")

    assert res.is_success is True
    assert "th0r3nt/JAWL" not in watchers_skill.client.state.tracked_repos
    watchers_skill.events.save_persisted_repos.assert_called_once()
    
    # Добавляем проверку на физическую отписку (если аккаунт включен)
    if watchers_skill.client.config.agent_account and watchers_skill.client.token:
        mock_github_client.request.assert_called_once_with("DELETE", "/repos/th0r3nt/JAWL/subscription")
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l2_interfaces.github.events import GithubEvents


@pytest.fixture
def github_events(mock_github_client, github_state, tmp_path):
    bus = MagicMock()
    bus.publish = AsyncMock()
    return GithubEvents(mock_github_client, github_state, bus, data_dir=tmp_path)


def test_github_events_parse_event(github_events):
    """Тест: парсинг сырых эвентов GitHub в красивый Markdown."""
    raw_push = {
        "type": "PushEvent",
        "actor": {"login": "th0r3nt"},
        "repo": {"name": "th0r3nt/JAWL"},
        "payload": {"commits": [{"message": "Fix bugs\nDetails"}]},
    }
    parsed = github_events._parse_github_event(raw_push)
    assert parsed is not None
    assert "запушил 1 коммит" in parsed
    assert "Fix bugs" in parsed

    raw_watch = {"type": "WatchEvent"}  # Мусорный эвент
    assert github_events._parse_github_event(raw_watch) is None


@pytest.mark.asyncio
async def test_github_events_poll_watched_repos(github_events, mock_github_client):
    """Тест: опрос отслеживаемых репозиториев и рассылка в EventBus."""
    github_events.state.tracked_repos = {"th0r3nt/JAWL": "100"}

    mock_github_client.request.return_value = [
        {
            "id": "102",
            "type": "IssuesEvent",
            "actor": {"login": "user"},
            "payload": {"action": "opened"},
        }
    ]

    await github_events._poll_watched_repos()

    # Проверяем, что стейт обновился
    assert github_events.state.tracked_repos["th0r3nt/JAWL"] == "102"
    assert len(github_events.state.recent_watcher_events) == 1
    # Проверяем публикацию в шину
    github_events.bus.publish.assert_called_once()


def test_github_events_persistence(github_events):
    """Тест: сохранение и загрузка отслеживаемых реп на диск."""
    github_events.state.tracked_repos = {"test/repo": "123"}
    github_events.save_persisted_repos()

    assert github_events._persistence_file.exists()

    # Очищаем стейт и загружаем заново
    github_events.state.tracked_repos = {}
    github_events._load_persisted_repos()
    assert github_events.state.tracked_repos["test/repo"] == "123"

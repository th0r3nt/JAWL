import pytest
from src.l2_interfaces.github.skills.pull_requests import GithubPullRequests


@pytest.mark.asyncio
async def test_list_pull_requests(mock_github_client):
    skills = GithubPullRequests(mock_github_client)

    mock_github_client.request.return_value = [
        {
            "number": 1,
            "title": "Fix bug",
            "user": {"login": "alex"},
            "head": {"ref": "patch-1"},
        }
    ]

    res = await skills.list_pull_requests("th0r3nt", "JAWL")

    assert res.is_success is True
    assert "#1" in res.message
    assert "Fix bug" in res.message


@pytest.mark.asyncio
async def test_get_pull_request_diff(mock_github_client):
    skills = GithubPullRequests(mock_github_client)

    fake_diff = "--- a/main.py\n+++ b/main.py\n+print('fix')"
    mock_github_client.request.return_value = fake_diff

    res = await skills.get_pull_request_diff("th0r3nt", "JAWL", 42)

    assert res.is_success is True
    assert "print('fix')" in res.message

    # Проверяем, что передали правильный Accept Header для diff
    call_args = mock_github_client.request.call_args
    assert call_args[1]["response_format"] == "text"
    assert call_args[1]["extra_headers"]["Accept"] == "application/vnd.github.v3.diff"

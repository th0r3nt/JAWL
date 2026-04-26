import pytest
from src.l2_interfaces.github.skills.issues import GithubIssues


@pytest.mark.asyncio
async def test_list_issues(mock_github_client):
    skills = GithubIssues(mock_github_client)
    mock_github_client.request.return_value = [
        {"number": 42, "title": "Crash on startup", "user": {"login": "tester"}, "comments": 2}
    ]

    res = await skills.list_issues("th0r3nt", "JAWL", state="open")

    assert res.is_success is True
    assert "#42" in res.message
    assert "Crash on startup" in res.message


@pytest.mark.asyncio
async def test_create_issue_requires_agent_account(mock_github_client):
    """Тест: агент не может создать Issue без Agent Account."""
    skills = GithubIssues(mock_github_client)
    mock_github_client.config.agent_account = False

    res = await skills.create_issue("th0r3nt", "JAWL", "New bug")
    assert res.is_success is False
    assert "нужно включить" in res.message
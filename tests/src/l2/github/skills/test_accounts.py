import pytest
from src.l2_interfaces.github.skills.accounts import GithubAccounts


@pytest.mark.asyncio
async def test_get_user_profile(mock_github_client):
    skills = GithubAccounts(mock_github_client)
    mock_github_client.request.return_value = {
        "login": "th0r3nt",
        "name": "Thor",
        "bio": "AI Developer"
    }

    res = await skills.get_user_profile("th0r3nt")

    assert res.is_success is True
    assert "Thor" in res.message
    assert "AI Developer" in res.message
import pytest
import base64
from unittest.mock import patch
from src.l2_interfaces.github.skills.repositories import GithubRepositories


@pytest.mark.asyncio
async def test_get_repo_info(mock_github_client):
    skills = GithubRepositories(mock_github_client)
    mock_github_client.request.return_value = {
        "full_name": "th0r3nt/JAWL",
        "stargazers_count": 42,
        "language": "Python",
    }

    res = await skills.get_repo_info("th0r3nt", "JAWL")

    assert res.is_success is True
    assert "th0r3nt/JAWL" in res.message
    assert "42" in res.message


@pytest.mark.asyncio
async def test_read_file_content(mock_github_client):
    skills = GithubRepositories(mock_github_client)

    # Имитируем ответ GitHub API (base64 encoded)
    fake_content = base64.b64encode(b"print('hello')").decode("utf-8")
    mock_github_client.request.return_value = {"content": fake_content}

    res = await skills.read_file_content("th0r3nt", "JAWL", "main.py")

    assert res.is_success is True
    assert "print('hello')" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.github.skills.repositories.validate_sandbox_path")
async def test_download_repository(mock_validate, mock_github_client, tmp_path):
    skills = GithubRepositories(mock_github_client)

    mock_path = tmp_path / "repo.zip"
    mock_validate.return_value = mock_path

    # Имитируем бинарный ответ ZIP архива
    mock_github_client.request.return_value = b"PK\x03\x04fake_zip_data"

    res = await skills.download_repository("th0r3nt", "JAWL", "jawl.zip")

    assert res.is_success is True
    assert mock_path.exists()
    assert mock_path.read_bytes() == b"PK\x03\x04fake_zip_data"
    mock_github_client.request.assert_called_once_with(
        "GET", "/repos/th0r3nt/JAWL/zipball", response_format="binary"
    )

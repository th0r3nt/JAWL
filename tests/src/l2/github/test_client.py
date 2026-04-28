import pytest
from unittest.mock import patch, MagicMock
from src.l2_interfaces.github.client import GithubClient, GithubHTTPError


@pytest.mark.asyncio
@patch("src.l2_interfaces.github.client.urllib.request.urlopen")
async def test_github_client_request_json(mock_urlopen, github_state, github_config):
    client = GithubClient(state=github_state, config=github_config, token="fake_token")
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"login": "th0r3nt"}'
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    result = await client.request("GET", "/user")
    assert result == {"login": "th0r3nt"}


@pytest.mark.asyncio
@patch("src.l2_interfaces.github.client.urllib.request.urlopen")
async def test_github_client_http_error(mock_urlopen, github_state, github_config):
    import urllib.error

    client = GithubClient(state=github_state, config=github_config)

    mock_fp = MagicMock()
    mock_fp.read.return_value = b'{"message": "Not Found"}'

    error_mock = urllib.error.HTTPError(
        url="http://fake", code=404, msg="Not Found", hdrs={}, fp=mock_fp
    )
    mock_urlopen.side_effect = error_mock

    with pytest.raises(GithubHTTPError) as exc:
        await client.request("GET", "/fake_endpoint")

    assert exc.value.status == 404

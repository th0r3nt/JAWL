"""
Low-level client for communicating with GitHub REST API.

Automatically handles pagination, rate limits, and manages authorization modes
(Full Access vs Read-Only). Isolates network logic from agent skills.
"""

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional, Union, Literal, Dict

from src.__init__ import __version__

from src.utils.logger import main_logger
from src.utils.settings import GithubConfig
from src.l2_interfaces.github.state import GithubState


class GithubHTTPError(Exception):
    """Custom exception for handling GitHub API errors."""

    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self.payload = payload
        msg = payload.get("message") if isinstance(payload, dict) else str(payload)
        super().__init__(f"HTTP {status}: {msg}")


class GithubClient:
    """
    GitHub REST API Client.
    Stateful - stores state, manages authorization and caching.
    """

    def __init__(
        self,
        state: GithubState,
        config: GithubConfig,
        token: Optional[str] = None,
    ) -> None:
        """
        Initializes the GitHub client.

        Args:
            state: L0 state (agent dashboard).
            config: Interface configuration.
            token: Optional Personal Access Token for authorization.
        """
        self.state = state
        self.config = config
        self.token = token

        self.api_base = "https://api.github.com"
        self.user_agent = f"JAWL-Agent/{__version__}"

    async def start(self) -> None:
        """
        Starts on system startup.
        Validates the token and determines the available mode (Agent Account or Read-Only).
        """
        self.state.is_online = True

        if self.config.agent_account and self.token:
            try:
                data = await self.request("GET", "/user")
                login = data.get("login", "Unknown") if isinstance(data, dict) else "Unknown"
                self.state.account_info = f"Agent account online. Logged in as @{login}"

                main_logger.info(f"[Github] Successful authorization as @{login}")

            except GithubHTTPError as e:
                self.state.account_info = f"Auth Failed (HTTP {e.status}). Read-Only mode."
                main_logger.error(f"[Github] Authorization error: {e}. Verify token.")
                self.config.agent_account = False  # Fallback

        else:
            auth_type = "token" if self.token else "No token (60 req/hr)"
            self.state.account_info = f"Agent account offline. Read-Only ({auth_type})"

            main_logger.info("[Github] Initialized in Read-Only mode.")

    async def stop(self) -> None:
        """Stops client (sets offline status)."""
        self.state.is_online = False

    def _build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Assembles HTTP headers taking authorization into account."""
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra:
            headers.update(extra)
        return headers

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        response_format: Literal["json", "text", "binary"] = "json",
    ) -> Union[dict, list, str, bytes, None]:
        """
        Low-level asynchronous HTTP request to the GitHub API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API endpoint (e.g. '/user/repos').
            params: Request query parameters.
            body: Payload (JSON).
            extra_headers: Additional headers.
            response_format: Expected response format ('json', 'text', 'binary').

        Returns:
            Parsed response from the API depending on response_format.

        Raises:
            GithubHTTPError: If the server returned an error (4xx, 5xx).
        """

        def _do_request() -> Union[dict, list, str, bytes, None]:
            url = f"{self.api_base}/{path.lstrip('/')}"
            if params:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{urllib.parse.urlencode(params)}"

            data_bytes = None
            if body is not None:
                data_bytes = json.dumps(body).encode("utf-8")

            headers = self._build_headers(extra_headers)

            if method.upper() in ("PUT", "DELETE") and data_bytes is None:
                data_bytes = b""
                headers["Content-Length"] = "0"

            req = urllib.request.Request(
                url,
                data=data_bytes,
                method=method.upper(),
                headers=headers,
            )

            try:
                with urllib.request.urlopen(
                    req, timeout=self.config.request_timeout_sec
                ) as resp:
                    if response_format == "binary":
                        return resp.read()

                    raw = resp.read().decode("utf-8", errors="replace")

                    if response_format == "text":
                        return raw

                    return json.loads(raw) if raw else None

            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
                try:
                    parsed: Any = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    parsed = raw
                raise GithubHTTPError(e.code, parsed) from e

        return await asyncio.to_thread(_do_request)

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Returns a formatted context block for the agent's system prompt.
        """
        desc = "Description: GitHub REST API and local Git operations."

        if not self.state.is_online:
            return f"### GITHUB [OFF]\n{desc}\nThe interface is disabled."

        agent_dashboard = ""
        if self.config.agent_account and self.token:
            agent_dashboard = (
                f"\n* Current account repositories (Top 5 by activity):\n  {self.state.own_repos.replace(chr(10), chr(10)+'  ')}\n"
                f"\n* Notifications:\n  {self.state.unread_notifications.replace(chr(10), chr(10)+'  ')}"
            )

        watchers_block = ""
        if self.state.tracked_repos:
            repos_list = ", ".join(self.state.tracked_repos.keys())
            events_str = (
                "\n".join(self.state.recent_watcher_events)
                if self.state.recent_watcher_events
                else "  No recent events."
            )
            watchers_block = f"\n\n* Tracked repositories: {repos_list}\n* Latest events in repositories:\n{events_str}\n"

        return (
            f"### GITHUB [ON]\n"
            f"{desc}\n"
            f"* Auth: {self.state.account_info}"
            f"{agent_dashboard}"
            f"{watchers_block}\n"
            f"* Query history:\n{self.state.github_history}"
        )

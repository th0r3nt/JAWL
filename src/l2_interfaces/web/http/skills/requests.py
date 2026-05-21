"""
Skills for sending low-level HTTP/REST requests.

Used for interacting with external JSON/API services
and direct file downloading without the overhead of a full browser.
"""

import asyncio
import urllib.parse
import urllib.request
import urllib.error
from typing import Optional, Tuple

from src import __version__
from src.utils.logger import main_logger
from src.utils._tools import truncate_text, validate_sandbox_path

from src.l2_interfaces.web.http.client import WebHTTPClient

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

_ALLOWED_URL_SCHEMES = ("http", "https")


def _ensure_http_scheme(url: str) -> Optional[str]:
    """Verifies protocol safety (blocks attempts to load file://)."""
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_URL_SCHEMES:
        return (
            f"Forbidden URL scheme: '{scheme or '<empty>'}'. "
            "Only http:// and https:// are allowed."
        )
    return None


class WebHTTPRequests:
    """Skills for sending raw HTTP requests and downloading files."""

    def __init__(self, client: WebHTTPClient) -> None:
        self.client = client

    @skill(swarm=[Subagents.WEB_RESEARCHER])
    async def request(
        self, url: str, method: str = "GET", headers: Optional[dict] = None
    ) -> SkillResult:
        """
        Makes HTTP request.

        method: HTTP method.
        headers: Custom HTTP headers dict.
        """

        limit = self.client.config.max_response_chars

        scheme_error = _ensure_http_scheme(url)
        if scheme_error:
            return SkillResult.fail(scheme_error)

        def _make_request() -> Tuple[int, str]:
            req_headers = headers or {"User-Agent": f"JAWL-Agent/{__version__}"}
            req = urllib.request.Request(url, method=method.upper(), headers=req_headers)

            try:
                with urllib.request.urlopen(
                    req, timeout=self.client.config.request_timeout_sec
                ) as response:
                    status = response.status
                    body = response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                status = e.code
                body = e.read().decode("utf-8", errors="replace")

            body = truncate_text(body, limit)
            return status, body

        try:
            status_code, content = await asyncio.to_thread(_make_request)
            main_logger.info(
                f"[Web HTTP] {method.upper()} request to {url} (Status: {status_code})"
            )

            self.client.state.add_history(f"{method.upper()} {url} (Status: {status_code})")
            return SkillResult.ok(f"Status: {status_code}\n\nResponse body:\n{content}")

        except Exception as e:
            return SkillResult.fail(f"Error during HTTP request: {e}")

    @skill()
    async def download_file(self, url: str, dest_filename: str) -> SkillResult:
        """
        Downloads file to disk (sandbox/download/).

        dest_filename: Output filename.
        """

        try:
            scheme_error = _ensure_http_scheme(url)
            if scheme_error:
                return SkillResult.fail(scheme_error)

            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"sandbox/_system/download/{dest_filename}"

            # Protect the system - write only to the sandbox
            safe_path = validate_sandbox_path(dest_filename)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            def _download() -> None:
                req = urllib.request.Request(
                    url, headers={"User-Agent": f"JAWL-Agent/{__version__}"}
                )
                with urllib.request.urlopen(req, timeout=30) as response, open(
                    safe_path, "wb"
                ) as out_file:
                    out_file.write(response.read())

            await asyncio.to_thread(_download)

            main_logger.info(f"[Web HTTP] File {safe_path.name} downloaded from {url}")
            self.client.state.add_history(f"Download: {url} -> {safe_path.name}")
            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error during file downloading: {e}")

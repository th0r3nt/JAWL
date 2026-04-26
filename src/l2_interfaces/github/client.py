import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional, Union

from src.utils.logger import system_logger
from src.utils.settings import GithubConfig
from src.l0_state.interfaces.state import GithubState


class GithubHTTPError(Exception):
    def __init__(self, status: int, payload: Any):
        self.status = status
        self.payload = payload
        msg = payload.get("message") if isinstance(payload, dict) else str(payload)
        super().__init__(f"HTTP {status}: {msg}")


class GithubClient:
    """
    Клиент GitHub REST API.
    Stateful - хранит стейт и управляет авторизацией.
    """

    def __init__(
        self,
        state: GithubState,
        config: GithubConfig,
        token: Optional[str] = None,
    ):
        self.state = state
        self.config = config
        self.token = token

        self.api_base = "https://api.github.com"
        self.user_agent = "jawl-agent/1.0"

    async def start(self) -> None:
        """Запускается при старте системы. Чекает токен, если нужен аккаунт."""

        self.state.is_online = True

        if self.config.agent_account and self.token:
            try:
                # Дергаем профиль, чтобы убедиться, что токен валидный
                data = await self.request("GET", "/user")
                login = data.get("login", "Unknown")
                self.state.account_info = f"Agent account online. Logged in as @{login}"
                system_logger.info(f"[Github] Успешная авторизация как @{login}")

            except GithubHTTPError as e:
                self.state.account_info = (
                    f"Auth Failed (HTTP {e.status}). Read-Only режим."
                )
                system_logger.error(f"[Github] Ошибка авторизации: {e}. Проверьте токен.")
                self.config.agent_account = False  # Фоллбэк
        else:
            auth_type = "token" if self.token else "No token (60 req/hr)"
            self.state.account_info = f"Agent account offline. Read-Only ({auth_type})"
            system_logger.info("[Github] Инициализирован в Read-Only режиме.")

    async def stop(self) -> None:
        self.state.is_online = False

    def _build_headers(self, extra: Optional[dict] = None) -> dict:
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
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
    ) -> Union[dict, list, None]:
        """Низкоуровневый асинхронный HTTP-запрос к API GitHub."""

        def _do_request():
            url = f"{self.api_base}/{path.lstrip('/')}"
            if params:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{urllib.parse.urlencode(params)}"

            data_bytes = None
            if body is not None:
                data_bytes = json.dumps(body).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=data_bytes,
                method=method.upper(),
                headers=self._build_headers(extra_headers),
            )

            try:
                with urllib.request.urlopen(
                    req, timeout=self.config.request_timeout_sec
                ) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
                try:
                    parsed: Any = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    parsed = raw
                raise GithubHTTPError(e.code, parsed) from e

        return await asyncio.to_thread(_do_request)

    async def get_context_block(self, **kwargs) -> str:
        """Отдает блок контекста для L3."""
        if not self.state.is_online:
            return "### GITHUB [OFF]\nИнтерфейс отключен."

        return f"### GITHUB [ON]\n* Auth: {self.state.account_info}\n* История запросов:\n{self.state.github_history}"

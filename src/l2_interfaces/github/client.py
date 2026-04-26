import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional, Union, Literal

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
    Stateful - хранит стейт, управляет авторизацией и фоновым обновлением дашборда.
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

        self._polling_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Запускается при старте системы. Чекает токен, если нужен аккаунт."""

        self.state.is_online = True

        if self.config.agent_account and self.token:
            try:
                # Дергаем профиль, чтобы убедиться, что токен валидный
                data = await self.request("GET", "/user")
                login = data.get("login", "Unknown") if isinstance(data, dict) else "Unknown"
                self.state.account_info = f"Agent account online. Logged in as @{login}"
                system_logger.info(f"[Github] Успешная авторизация как @{login}")

                # Запускаем фоновое обновление дашборда аккаунта
                self._polling_task = asyncio.create_task(self._poll_account_state())

            except GithubHTTPError as e:
                self.state.account_info = f"Auth Failed (HTTP {e.status}). Read-Only режим."
                system_logger.error(f"[Github] Ошибка авторизации: {e}. Проверьте токен.")
                self.config.agent_account = False  # Фоллбэк
        else:
            auth_type = "token" if self.token else "No token (60 req/hr)"
            self.state.account_info = f"Agent account offline. Read-Only ({auth_type})"
            system_logger.info("[Github] Инициализирован в Read-Only режиме.")

    async def stop(self) -> None:
        self.state.is_online = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

    async def _poll_account_state(self):
        """
        Фоновый сбор данных об аккаунте агента для дашборда (L0 State). 
        Выполняется раз в N минут.
        """

        while self.state.is_online:
            try:
                # Получаем свои репозитории (топ-5 недавно обновленных)
                repos_data = await self.request(
                    "GET", "/user/repos", params={"sort": "updated", "per_page": 5}
                )
                if repos_data and isinstance(repos_data, list):
                    repo_lines = []
                    for r in repos_data:
                        name = r.get("full_name")
                        stars = r.get("stargazers_count", 0)
                        is_fork = " (Fork)" if r.get("fork") else ""
                        repo_lines.append(f"- {name}{is_fork} ({stars}⭐)")
                    self.state.own_repos = (
                        "\n".join(repo_lines) if repo_lines else "У вас пока нет репозиториев."
                    )

                # Получаем непрочитанные уведомления
                notif_data = await self.request(
                    "GET", "/notifications", params={"all": "false"}
                )
                if isinstance(notif_data, list):
                    count = len(notif_data)
                    if count == 0:
                        self.state.unread_notifications = "Нет новых уведомлений."
                    else:
                        notif_lines = [f"У вас {count} непрочитанных уведомлений:"]
                        for n in notif_data[:3]:
                            title = n.get("subject", {}).get("title", "No title")
                            repo = (n.get("repository") or {}).get("full_name", "Unknown")
                            n_type = n.get("subject", {}).get("type", "Unknown")
                            notif_lines.append(f"- [{repo}] {n_type}: {title}")
                        self.state.unread_notifications = "\n".join(notif_lines)

            except Exception as e:
                system_logger.debug(f"[Github] Ошибка фонового обновления профиля: {e}")

            # Используем параметр из конфига
            await asyncio.sleep(self.config.polling_interval_sec)

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
        response_format: Literal["json", "text", "binary"] = "json",
    ) -> Union[dict, list, str, bytes, None]:
        """
        Низкоуровневый асинхронный HTTP-запрос к API GitHub.
        """

        def _do_request():
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

    async def get_context_block(self, **kwargs) -> str:
        """Отдает блок контекста для L3."""
        if not self.state.is_online:
            return "### GITHUB [OFF]\nИнтерфейс отключен."

        agent_dashboard = ""
        if self.config.agent_account and self.token:
            agent_dashboard = (
                f"\n* Текущие репозитории (Топ-5 по активности):\n  {self.state.own_repos.replace(chr(10), chr(10)+'  ')}\n"
                f"* Уведомления:\n  {self.state.unread_notifications.replace(chr(10), chr(10)+'  ')}"
            )

        return (
            f"### GITHUB [ON]\n"
            f"* Auth: {self.state.account_info}"
            f"{agent_dashboard}\n"
            f"* История запросов:\n{self.state.github_history}"
        )

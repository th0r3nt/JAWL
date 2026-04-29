import asyncio
import urllib.parse
import urllib.request
import urllib.error
from typing import Optional

from src import __version__
from src.utils.logger import system_logger
from src.utils._tools import truncate_text, validate_sandbox_path
from src.l3_agent.skills.registry import SkillResult, skill
from src.l2_interfaces.web.http.client import WebHTTPClient


_ALLOWED_URL_SCHEMES = ("http", "https")


def _ensure_http_scheme(url: str) -> Optional[str]:
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_URL_SCHEMES:
        return (
            f"Запрещённая схема URL: '{scheme or '<пусто>'}'. "
            "Разрешены только http:// и https://."
        )
    return None


class WebHTTPRequests:
    """Навыки для отправки сырых HTTP-запросов и скачивания файлов."""

    def __init__(self, client: WebHTTPClient):
        self.client = client

    @skill()
    async def http_request(
        self, url: str, method: str = "GET", headers: Optional[dict] = None
    ) -> SkillResult:
        """
        Отправляет HTTP-запрос и возвращает ответ.
        """

        limit = self.client.config.max_response_chars

        scheme_error = _ensure_http_scheme(url)
        if scheme_error:
            return SkillResult.fail(scheme_error)

        def _make_request():
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
            system_logger.info(
                f"[Web HTTP] {method.upper()} запрос к {url} (Статус: {status_code})"
            )

            self.client.state.add_history(f"{method.upper()} {url} (Status: {status_code})")
            return SkillResult.ok(f"Статус: {status_code}\n\nТело ответа:\n{content}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при HTTP-запросе: {e}")

    @skill()
    async def download_file(self, url: str, dest_filename: str) -> SkillResult:
        """
        Скачивает файл из сети на диск. 
        Сохраняет строго в песочницу (sandbox/download/).
        """

        try:
            scheme_error = _ensure_http_scheme(url)
            if scheme_error:
                return SkillResult.fail(scheme_error)

            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"_system/download/{dest_filename}"

            # Защищаем систему - пишем только в песочницу
            safe_path = validate_sandbox_path(dest_filename)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            def _download():
                req = urllib.request.Request(
                    url, headers={"User-Agent": f"JAWL-Agent/{__version__}"}
                )
                with urllib.request.urlopen(req, timeout=30) as response, open(
                    safe_path, "wb"
                ) as out_file:
                    out_file.write(response.read())

            await asyncio.to_thread(_download)

            system_logger.info(f"[Web HTTP] Файл {safe_path.name} скачан из {url}")
            self.client.state.add_history(f"Download: {url} -> {safe_path.name}")
            return SkillResult.ok(
                f"Файл успешно скачан и сохранен по пути: sandbox/{safe_path.name}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        
        except Exception as e:
            return SkillResult.fail(f"Ошибка при скачивании файла: {e}")

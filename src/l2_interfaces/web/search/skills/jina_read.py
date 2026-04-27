import asyncio
import urllib.request
import urllib.error

from src.utils.logger import system_logger
from src.utils._tools import truncate_text
from src.l2_interfaces.web.search.client import WebSearchClient
from src.l3_agent.skills.registry import skill, SkillResult


class JinaReader:
    def __init__(self, client: WebSearchClient):
        self.client = client

    async def read_raw(self, url: str) -> str | None:
        def _fetch():
            req_url = f"https://r.jina.ai/{url}"
            req = urllib.request.Request(req_url)
            req.add_header("User-Agent", "JAWL-Agent/1.0")

            with urllib.request.urlopen(req, timeout=self.client.timeout) as response:
                return response.read().decode("utf-8", errors="replace")

        return await asyncio.to_thread(_fetch)

    @skill()
    async def read_webpage(self, url: str) -> SkillResult:
        """
        Читает текстовое содержимое веб-страницы по URL.
        """

        try:
            text = await self.read_raw(url)
            if not text:
                return SkillResult.fail(
                    f"Ошибка: не удалось прочитать {url} (пустой ответ от Jina)."
                )

            total_len = len(text)
            if total_len > self.client.max_page_chars:
                text = truncate_text(text, self.client.max_page_chars, "... [Текст обрезан]")
                system_logger.info(f"[Web] Прочитана страница (Jina, с обрезкой): {url}")
            else:
                system_logger.info(f"[Web] Прочитана страница (Jina, полностью): {url}")

            header = (
                f"[Веб-страница (Jina) | Прочитано: {len(text)}/{total_len} симв.]\n{'='*40}\n"
            )
            self.client.state.add_history(f"Чтение страницы (Jina): {url}")
            return SkillResult.ok(header + text)

        except urllib.error.HTTPError as e:
            return SkillResult.fail(f"Ошибка HTTP при чтении {url}: {e.code} {e.reason}")
        
        except Exception as e:
            return SkillResult.fail(f"Ошибка парсинга страницы (Jina): {e}")

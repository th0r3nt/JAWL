import base64
import asyncio
from typing import Optional

from src.l2_interfaces.github.client import GithubClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger
from src.utils._tools import truncate_text, validate_sandbox_path, format_size


class GithubRepositories:
    """Навыки для работы с репозиториями и кодом."""

    def __init__(self, client: GithubClient):
        self.client = client

    @skill()
    async def get_repo_info(self, owner: str, repo: str) -> SkillResult:
        """
        Возвращает метаданные репозитория (stars, forks, описание, язык).
        """

        try:
            data = await self.client.request("GET", f"/repos/{owner}/{repo}")
            self.client.state.add_history(f"get_repo: {owner}/{repo}")

            lines = [
                f"Репозиторий: {data.get('full_name')}",
                f"Описание: {data.get('description', 'Нет')}",
                f"Звезды: {data.get('stargazers_count')} | Форки: {data.get('forks_count')}",
                f"Язык: {data.get('language')} | Ветка: {data.get('default_branch')}",
                f"Открытых issues: {data.get('open_issues_count')}",
            ]
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении репозитория: {e}")

    @skill()
    async def search_code(self, query: str, per_page: int = 10) -> SkillResult:
        """
        [Требует auth-токен] Ищет код по GitHub.
        """

        if not self.client.token:
            return SkillResult.fail("Ошибка: Поиск кода требует наличия GITHUB_TOKEN.")

        try:
            params = {"q": query, "per_page": per_page}
            data = await self.client.request("GET", "/search/code", params=params)
            self.client.state.add_history(f"search_code: '{query}'")

            items = data.get("items", [])
            if not items:
                return SkillResult.ok(f"Код по запросу '{query}' не найден.")

            lines = [f"Найдено: {data.get('total_count')} (показаны топ {len(items)}):"]
            for item in items:
                repo_name = (item.get("repository") or {}).get("full_name")
                lines.append(
                    f"- [{repo_name}] {item.get('path')} (URL: {item.get('html_url')})"
                )

            system_logger.info(f"[Github] Выполнен поиск кода: '{query}'")
            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске кода: {e}")

    @skill()
    async def read_file_content(
        self, owner: str, repo: str, path: str, ref: Optional[str] = None
    ) -> SkillResult:
        """
        Читает содержимое файла из репозитория GitHub.
        """

        try:
            params = {"ref": ref} if ref else None
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/contents/{path}", params=params
            )

            if isinstance(data, list):
                return SkillResult.fail("Ошибка: Указан путь к директории, а не к файлу.")

            content_b64 = data.get("content", "")
            content = base64.b64decode(content_b64).decode("utf-8", errors="replace")

            # Защита контекста
            content = truncate_text(
                content, 10000, "... [Файл обрезан для экономии контекста]"
            )

            self.client.state.add_history(f"read_file: {owner}/{repo}:{path}")
            system_logger.info(f"[Github] Прочитан файл {path} из {owner}/{repo}")

            return SkillResult.ok(f"Содержимое {path}:\n```\n{content}\n```")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении файла: {e}")

    @skill()
    async def list_recent_commits(
        self, owner: str, repo: str, per_page: int = 10
    ) -> SkillResult:
        """Возвращает последние коммиты репозитория."""

        try:
            params = {"per_page": per_page}
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/commits", params=params
            )
            self.client.state.add_history(f"list_commits: {owner}/{repo}")

            if not data:
                return SkillResult.ok("Коммитов не найдено.")

            lines = [f"Последние коммиты {owner}/{repo}:"]
            for c in data:
                sha = (c.get("sha") or "")[:7]
                commit_data = c.get("commit", {})
                msg = commit_data.get("message", "").split("\n")[0]
                author = (commit_data.get("author") or {}).get("name", "Unknown")
                lines.append(f"- [{sha}] {msg} (by {author})")

            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении коммитов: {e}")

    @skill()
    async def download_repository(
        self, owner: str, repo: str, dest_filename: str, ref: Optional[str] = None
    ) -> SkillResult:
        """
        Скачивает репозиторий в виде ZIP-архива. Без .git файла. По умолчанию сохраняет в sandbox/download/.
        ref: Опционально (имя ветки, тег или коммит).
        """
        try:
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"download/{dest_filename}"

            safe_path = validate_sandbox_path(dest_filename)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            endpoint = f"/repos/{owner}/{repo}/zipball"
            if ref:
                endpoint += f"/{ref}"

            binary_data = await self.client.request("GET", endpoint, response_format="binary")

            if not binary_data:
                return SkillResult.fail("Не удалось скачать архив (пустой ответ от сервера).")

            def _save():
                with open(safe_path, "wb") as f:
                    f.write(binary_data)

            await asyncio.to_thread(_save)

            size_str = format_size(safe_path.stat().st_size)
            self.client.state.add_history(f"download_repo: {owner}/{repo}")
            system_logger.info(
                f"[Github] Репозиторий {owner}/{repo} скачан в {safe_path.name} ({size_str})"
            )

            return SkillResult.ok(
                f"Репозиторий успешно скачан в архив: sandbox/{safe_path.name} ({size_str})"
            )
        except PermissionError as e:
            return SkillResult.fail(str(e))
        
        except Exception as e:
            return SkillResult.fail(f"Ошибка при скачивании репозитория: {e}")

    @skill()
    async def star_repository(self, owner: str, repo: str) -> SkillResult:
        """[Требует Agent Account] Ставит звезду репозиторию."""

        if not self.client.config.agent_account:
            return SkillResult.fail("Ошибка: Для этого действия нужен Agent Account.")

        try:
            await self.client.request("PUT", f"/user/starred/{owner}/{repo}")
            self.client.state.add_history(f"star: {owner}/{repo}")
            system_logger.info(f"[Github] Поставлена звезда репозиторию {owner}/{repo}")
            return SkillResult.ok(f"Звезда успешно поставлена репозиторию {owner}/{repo}.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при постановке звезды: {e}")

    @skill()
    async def unstar_repository(self, owner: str, repo: str) -> SkillResult:
        """[Требует Agent Account] Убирает звезду с репозитория."""

        if not self.client.config.agent_account:
            return SkillResult.fail("Ошибка: Для этого действия нужен Agent Account.")

        try:
            await self.client.request("DELETE", f"/user/starred/{owner}/{repo}")
            self.client.state.add_history(f"unstar: {owner}/{repo}")
            system_logger.info(f"[Github] Убрана звезда с репозитория {owner}/{repo}")
            return SkillResult.ok(f"Звезда успешно убрана с репозитория {owner}/{repo}.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении звезды: {e}")

    @skill()
    async def list_branches(self, owner: str, repo: str, per_page: int = 30) -> SkillResult:
        """Возвращает список веток репозитория."""
        try:
            params = {"per_page": per_page}
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/branches", params=params
            )
            self.client.state.add_history(f"list_branches: {owner}/{repo}")

            if not data:
                return SkillResult.ok("Ветки не найдены.")

            lines = [f"Ветки репозитория {owner}/{repo}:"]
            for branch in data:
                protected = " (Защищена)" if branch.get("protected") else ""
                lines.append(f"- {branch.get('name')}{protected}")

            return SkillResult.ok("\n".join(lines))
        
        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка веток: {e}")

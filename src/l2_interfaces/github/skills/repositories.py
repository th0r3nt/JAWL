import base64
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Literal

from src.l2_interfaces.github.client import GithubClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger
from src.utils._tools import truncate_text, validate_sandbox_path, format_size


class GithubRepositories:
    """Навыки для работы с репозиториями и кодом."""

    def __init__(self, client: GithubClient):
        self.client = client

    @skill()
    async def search_repositories(
        self,
        query: str,
        sort: Optional[Literal["stars", "forks", "updated"]],
        per_page: int = 10,
    ) -> SkillResult:
        """
        Ищет репозитории по ключевым словам или темам.
        """

        try:
            params = {"q": query, "per_page": per_page}
            if sort:
                params["sort"] = sort

            data = await self.client.request("GET", "/search/repositories", params=params)
            self.client.state.add_history(f"search_repos: '{query}'")

            items = data.get("items", [])
            if not items:
                return SkillResult.ok(f"По запросу '{query}' репозитории не найдены.")

            lines = [
                f"Найдено репозиториев: {data.get('total_count')} (показаны топ {len(items)}):"
            ]
            for item in items:
                repo_name = item.get("full_name")
                stars = item.get("stargazers_count")
                lang = item.get("language") or "N/A"
                desc = item.get("description") or "Без описания"
                url = item.get("html_url")

                # Защищаем контекст от огромных описаний
                clean_desc = truncate_text(desc.replace("\n", " "), 150, "...")

                lines.append(
                    f"- [{repo_name}] ({stars}⭐ | {lang}) - {clean_desc}\n  URL: {url}"
                )

            system_logger.info(f"[Github] Выполнен поиск репозиториев: '{query}'")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске репозиториев: {e}")

    @skill()
    async def get_trending_repositories(
        self,
        period: Optional[Literal["daily", "weekly", "monthly"]],
        language: str = "",
        limit: int = 10,
    ) -> SkillResult:
        """
        Получает трендовые (самые популярные за последнее время) репозитории.
        language: Опциональный фильтр по языку программирования.
        """

        try:
            now = datetime.utcnow()
            if period == "daily":
                delta = timedelta(days=1)

            elif period == "weekly":
                delta = timedelta(days=7)

            elif period == "monthly":
                delta = timedelta(days=30)

            else:
                return SkillResult.fail(
                    "Ошибка: period должен быть 'daily', 'weekly' или 'monthly'."
                )

            # Формируем Dork-запрос (репозитории, созданные за указанный период, отсортированные по звездам)
            target_date = (now - delta).strftime("%Y-%m-%d")
            query = f"created:>{target_date}"
            if language:
                query += f" language:{language}"

            params = {"q": query, "sort": "stars", "order": "desc", "per_page": limit}

            data = await self.client.request("GET", "/search/repositories", params=params)
            self.client.state.add_history(f"trending_repos: {period} ({language or 'all'})")

            items = data.get("items", [])
            if not items:
                return SkillResult.ok(
                    "Не удалось найти трендовые репозитории по заданным критериям."
                )

            lang_str = f" для '{language}'" if language else ""
            lines = [f"Тренды GitHub ({period}){lang_str}:"]

            for item in items:
                repo_name = item.get("full_name")
                stars = item.get("stargazers_count")
                lang_val = item.get("language") or "N/A"
                desc = item.get("description") or "Без описания"
                url = item.get("html_url")

                clean_desc = truncate_text(desc.replace("\n", " "), 150, "...")

                lines.append(
                    f"- [{repo_name}] (+{stars}⭐ | {lang_val}) - {clean_desc}\n  URL: {url}"
                )

            system_logger.info(
                f"[Github] Запрошены тренды: {period}, lang: {language or 'all'}"
            )
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении трендов: {e}")

    @skill()
    async def get_repo_info(self, owner: str, repo: str) -> SkillResult:
        """
        Возвращает метаданные репозитория.
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
        """
        Возвращает последние коммиты репозитория.
        """

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
        Скачивает репозиторий в виде ZIP-архива. Без .git файлов. По умолчанию сохраняет в sandbox/download/.
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
    async def get_commit_details(self, owner: str, repo: str, commit_sha: str) -> SkillResult:
        """
        Возвращает детальную информацию о коммите, включая точные пути всех измененных файлов.
        """

        try:
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/commits/{commit_sha}"
            )
            self.client.state.add_history(f"get_commit: {owner}/{repo}@{commit_sha[:7]}")

            commit_msg = data.get("commit", {}).get("message", "Без описания")
            author = data.get("author", {}).get("login", "Unknown")
            stats = data.get("stats", {})
            files = data.get("files", [])

            lines = [
                f"Коммит: {commit_sha}",
                f"Автор: @{author}",
                f"Сообщение: {commit_msg}",
                f"Статистика: {stats.get('total')} изменений (+{stats.get('additions')} / -{stats.get('deletions')})",
                "\nИзмененные файлы:",
            ]

            if not files:
                lines.append("Нет измененных файлов.")
            else:
                for f in files:
                    status = f.get("status", "unknown")  # added, modified, removed, renamed
                    filename = f.get("filename", "unknown")
                    adds = f.get("additions", 0)
                    dels = f.get("deletions", 0)
                    lines.append(f"- [{status.upper()}] {filename} (+{adds} / -{dels})")

            system_logger.info(
                f"[Github] Прочитаны детали коммита {commit_sha[:7]} в {owner}/{repo}"
            )
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении деталей коммита: {e}")

    @skill()
    async def list_repo_directory(
        self, owner: str, repo: str, path: str = "", ref: Optional[str] = None
    ) -> SkillResult:
        """
        Просматривает содержимое (файлы и папки) в указанной директории GitHub репозитория.

        path: путь к директории (оставить пустым "" для просмотра корневой папки).
        ref: Опционально (имя ветки, тег или коммит).
        """

        try:
            params = {"ref": ref} if ref else None
            # Если path пустой, запрашиваем корень репозитория
            endpoint = (
                f"/repos/{owner}/{repo}/contents/{path.strip('/')}"
                if path
                else f"/repos/{owner}/{repo}/contents"
            )

            data = await self.client.request("GET", endpoint, params=params)
            self.client.state.add_history(f"list_repo_dir: {owner}/{repo}/{path}")

            # Если по указанному пути лежит файл, API возвращает dict, а не list
            if not isinstance(data, list):
                return SkillResult.fail(
                    "Ошибка: Указанный путь является файлом, а не директорией. Используйте навык 'read_file_content'."
                )

            lines = [f"Содержимое /{path} в {owner}/{repo}:"]
            for item in data:
                i_type = "📁 DIR " if item.get("type") == "dir" else "📄 FILE"
                name = item.get("name")
                size = item.get("size", 0)
                size_str = f" ({format_size(size)})" if item.get("type") == "file" else ""
                lines.append(f"- {i_type}: {name}{size_str}")

            system_logger.info(f"[Github] Прочитана директория /{path} в {owner}/{repo}")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при просмотре директории репозитория: {e}")

    @skill()
    async def star_repository(self, owner: str, repo: str) -> SkillResult:
        """
        [Требует Agent Account] Ставит звезду репозиторию.
        """

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
        """
        [Требует Agent Account] Убирает звезду с репозитория.
        """

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
        """
        Возвращает список веток репозитория.
        """

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

    @skill()
    async def create_repository(
        self, name: str, description: str = "", private: bool = False
    ) -> SkillResult:
        """
        [Требует Agent Account] Создает новый репозиторий в аккаунте агента.
        Автоматически инициализирует с README.md.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Ошибка: Для создания репозитория нужен Agent Account.")

        try:
            payload = {
                "name": name,
                "description": description,
                "private": private,
                "auto_init": True,  # Инициализируем пустым README
            }

            data = await self.client.request("POST", "/user/repos", body=payload)
            self.client.state.add_history(f"create_repo: {name}")

            repo_full_name = data.get("full_name")
            url = data.get("html_url")

            system_logger.info(f"[Github] Создан репозиторий {repo_full_name}")
            return SkillResult.ok(
                f"Репозиторий '{repo_full_name}' успешно создан.\nURL: {url}"
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании репозитория: {e}")

    @skill()
    async def fork_repository(self, owner: str, repo: str) -> SkillResult:
        """
        [Требует Agent Account] Делает форк (копию) чужого репозитория в аккаунт агента.
        Необходимо для отправки Pull Request-ов в чужие проекты.
        Внимание: процесс создания форка на стороне GitHub занимает пару секунд.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Ошибка: Для создания форка нужен Agent Account.")

        try:
            # POST /repos/{owner}/{repo}/forks
            data = await self.client.request("POST", f"/repos/{owner}/{repo}/forks")
            self.client.state.add_history(f"fork_repo: {owner}/{repo}")

            fork_name = data.get("full_name")
            url = data.get("html_url")

            system_logger.info(f"[Github] Сделан форк {owner}/{repo} -> {fork_name}")
            return SkillResult.ok(
                f"Форк успешно создан: '{fork_name}'. Теперь его можно клонировать локально.\nURL: {url}"
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при форке репозитория: {e}")

    @skill()
    async def create_gist(
        self, filename: str, content: str, description: str = "", public: bool = True
    ) -> SkillResult:
        """
        [Требует Agent Account] Создает Gist (публичный или приватный сниппет кода/текста).
        Удобно для того, чтобы поделиться логами, длинными скриптами или заметками по ссылке.
        """
        if not self.client.config.agent_account:
            return SkillResult.fail("Ошибка: Для создания Gist нужен Agent Account.")

        try:
            payload = {
                "description": description,
                "public": public,
                "files": {filename: {"content": content}},
            }

            data = await self.client.request("POST", "/gists", body=payload)
            self.client.state.add_history("create_gist")

            url = data.get("html_url")
            system_logger.info(f"[Github] Создан Gist: {filename}")

            return SkillResult.ok(f"Gist успешно создан.\nURL: {url}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании Gist: {e}")

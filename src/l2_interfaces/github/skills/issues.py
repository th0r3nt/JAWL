import urllib.parse
from typing import Literal, Optional

from src.l2_interfaces.github.client import GithubClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger
from src.utils._tools import truncate_text


class GithubIssues:
    """Навыки для работы с Issues и Pull Requests."""

    def __init__(self, client: GithubClient):
        self.client = client

    @skill()
    async def list_issues(
        self, owner: str, repo: str, state: Optional[Literal["open", "closed", "all"]] = "all", per_page: int = 10
    ) -> SkillResult:
        """
        Возвращает список issues репозитория.
        """

        try:
            params = urllib.parse.urlencode({"state": state, "per_page": per_page})
            data = await self.client.request("GET", f"/repos/{owner}/{repo}/issues?{params}")

            issues = [i for i in data if "pull_request" not in i]
            self.client.state.add_history(f"list_issues: {owner}/{repo} ({state})")

            if not issues:
                return SkillResult.ok(f"Нет {state} issues в репозитории.")

            lines = [f"Issues ({state}) в {owner}/{repo}:"]
            for i in issues:
                user = (i.get("user") or {}).get("login", "Unknown")
                lines.append(
                    f"- #{i.get('number')} | {i.get('title')} | by @{user} | Comments: {i.get('comments')}"
                )

            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении issues: {e}")

    @skill()
    async def read_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> SkillResult:
        """
        Читает issue и комментарии к нему.
        """

        try:
            # Сначала берем само issue
            issue = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/issues/{issue_number}"
            )

            # Затем комменты
            comments = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
            )
            self.client.state.add_history(f"read_issue: {owner}/{repo} #{issue_number}")

            author = (issue.get("user") or {}).get("login", "Unknown")
            body = truncate_text(issue.get("body") or "Без описания", 2000)

            lines = [
                f"Issue #{issue_number}: {issue.get('title')} (by @{author})",
                f"Описание:\n{body}\n---",
            ]

            if comments:
                lines.append("Комментарии:")
                for c in comments:
                    c_author = (c.get("user") or {}).get("login", "Unknown")
                    c_body = truncate_text(c.get("body") or "", 1000)
                    lines.append(f"[@{c_author}]: {c_body}\n-")
            else:
                lines.append("Нет комментариев.")

            system_logger.info(f"[Github] Прочитан Issue #{issue_number} в {owner}/{repo}")
            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении issue: {e}")

    @skill()
    async def create_issue(
        self, owner: str, repo: str, title: str, body: str = ""
    ) -> SkillResult:
        """
        [Требует Agent Account] Создает issue в репозитории.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail(
                "Ошибка: Для создания Issue нужно включить 'agent_account: true' в настройках и добавить токен."
            )

        try:
            data = await self.client.request(
                "POST",
                f"/repos/{owner}/{repo}/issues",
                body={"title": title, "body": body},
            )
            issue_num = data.get("number")
            self.client.state.add_history(f"create_issue: {owner}/{repo} #{issue_num}")
            system_logger.info(f"[Github] Создан Issue #{issue_num} в {owner}/{repo}")
            return SkillResult.ok(f"Issue успешно создано. URL: {data.get('html_url')}")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании issue: {e}")

    @skill()
    async def add_comment(
        self, owner: str, repo: str, issue_number: int, body: str
    ) -> SkillResult:
        """
        [Требует Agent Account] Добавляет комментарий к Issue или Pull Request.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail(
                "Ошибка: Для комментирования нужно включить 'agent_account: true'."
            )

        try:
            data = await self.client.request(
                "POST",
                f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                body={"body": body},
            )
            self.client.state.add_history(f"add_comment: {owner}/{repo} #{issue_number}")
            system_logger.info(f"[Github] Оставлен коммент в #{issue_number} ({owner}/{repo})")
            return SkillResult.ok(f"Комментарий успешно добавлен. URL: {data.get('html_url')}")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при добавлении комментария: {e}")

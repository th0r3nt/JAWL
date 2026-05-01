"""
Навыки для взаимодействия с GitHub Pull Requests.
"""

from src.l2_interfaces.github.client import GithubClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils._tools import truncate_text
from src.utils.logger import system_logger


class GithubPullRequests:
    """Навыки для работы с Pull Requests."""

    def __init__(self, client: GithubClient):
        self.client = client

    @skill()
    async def list_pull_requests(
        self, owner: str, repo: str, state: str = "open", per_page: int = 10
    ) -> SkillResult:
        """
        Возвращает список Pull Requests репозитория (state: open/closed/all).
        """
        
        try:
            params = {"state": state, "per_page": per_page}
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/pulls", params=params
            )

            self.client.state.add_history(f"list_prs: {owner}/{repo} ({state})")

            if not data:
                return SkillResult.ok(f"Нет {state} PRs в репозитории.")

            lines = [f"Pull Requests ({state}) в {owner}/{repo}:"]
            for pr in data:
                user = (pr.get("user") or {}).get("login", "Unknown")
                lines.append(
                    f"- #{pr.get('number')} | {pr.get('title')} | by @{user} | Ветка: {pr.get('head', {}).get('ref', '?')} -> {pr.get('base', {}).get('ref', '?')}"
                )

            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка PR: {e}")

    @skill()
    async def get_pull_request_diff(
        self, owner: str, repo: str, pull_number: int
    ) -> SkillResult:
        """
        Запрашивает Diff (добавленные/удаленные строки) конкретного Pull Request'а.
        
        Args:
            owner: Владелец репозитория.
            repo: Название репозитория.
            pull_number: Номер PR.
        """

        try:
            headers = {"Accept": "application/vnd.github.v3.diff"}
            diff_text = await self.client.request(
                "GET",
                f"/repos/{owner}/{repo}/pulls/{pull_number}",
                extra_headers=headers,
                response_format="text",
            )

            self.client.state.add_history(f"read_pr_diff: {owner}/{repo} #{pull_number}")

            if not diff_text:
                return SkillResult.ok("В этом PR нет изменений в коде.")

            diff_text = truncate_text(
                diff_text,
                20000,
                "\n... [Diff слишком большой, обрезан для экономии контекста]",
            )

            return SkillResult.ok(f"Diff для PR #{pull_number}:\n```diff\n{diff_text}\n```")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении Diff PR: {e}")

    @skill()
    async def create_pull_request(
        self, owner: str, repo: str, title: str, head: str, base: str = "main", body: str = ""
    ) -> SkillResult:
        """
        [Требует Agent Account] Создает новый Pull Request.

        Args:
            head: ветка, из которой переносим изменения.
            base: ветка, куда вливаем изменения.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail(
                "Ошибка: Для создания PR нужно включить 'agent_account: true' в настройках и добавить токен."
            )

        try:
            payload = {"title": title, "head": head, "base": base, "body": body}

            data = await self.client.request(
                "POST",
                f"/repos/{owner}/{repo}/pulls",
                body=payload,
            )

            pr_num = data.get("number")
            self.client.state.add_history(f"create_pr: {owner}/{repo} #{pr_num}")
            system_logger.info(f"[Github] Создан Pull Request #{pr_num} в {owner}/{repo}")

            return SkillResult.ok(f"Pull Request успешно создан. URL: {data.get('html_url')}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании Pull Request: {e}")

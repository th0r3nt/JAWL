"""
Skills for interacting with GitHub Pull Requests.
"""

from src.utils._tools import truncate_text
from src.utils.logger import main_logger

from src.l2_interfaces.github.client import GithubClient

from src.l3_agent.skills.registry import SkillResult, skill
from src.l2_interfaces.github.decorators import require_agent_account


class GithubPullRequests:
    """Skills for working with Pull Requests."""

    def __init__(self, client: GithubClient):
        self.client = client

    @skill()
    async def list_pull_requests(
        self, owner: str, repo: str, state: str = "open", per_page: int = 10
    ) -> SkillResult:
        """
        Returns list of repository Pull Requests.
        """

        try:
            params = {"state": state, "per_page": per_page}
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/pulls", params=params
            )

            self.client.state.add_history(f"list_prs: {owner}/{repo} ({state})")

            if not data:
                return SkillResult.ok(f"No {state} PRs in the repository.")

            lines = [f"Pull Requests ({state}) in {owner}/{repo}:"]
            for pr in data:
                user = (pr.get("user") or {}).get("login", "Unknown")
                lines.append(
                    f"- #{pr.get('number')} | {pr.get('title')} | by @{user} | Branch: {pr.get('head', {}).get('ref', '?')} -> {pr.get('base', {}).get('ref', '?')}"
                )

            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Error retrieving PR list: {e}")

    @skill()
    async def get_pull_request_diff(
        self, owner: str, repo: str, pull_number: int
    ) -> SkillResult:
        """
        Fetches Diff of specific Pull Request.
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
                return SkillResult.ok("There are no code changes in this PR.")

            diff_text = truncate_text(
                diff_text,
                20000,
                "\n... [Diff is too large, truncated to save context]",
            )

            return SkillResult.ok(f"Diff for PR #{pull_number}:\n```diff\n{diff_text}\n```")

        except Exception as e:
            return SkillResult.fail(f"Error reading Diff PR: {e}")

    @skill()
    @require_agent_account()
    async def create_pull_request(
        self, owner: str, repo: str, title: str, head: str, base: str = "main", body: str = ""
    ) -> SkillResult:
        """
        Creates new Pull Request.

        head: Branch containing changes.
        base: Branch to merge into.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail(
                "Error: Creating a PR requires 'agent_account: true' enabled in settings and a token added."
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
            main_logger.info(f"[Github] Created Pull Request #{pr_num} in {owner}/{repo}")

            return SkillResult.ok(f"True. URL: {data.get('html_url')}")

        except Exception as e:
            return SkillResult.fail(f"Error creating Pull Request: {e}")

"""
Agent skills for working with GitHub Issues and comments.
"""

import urllib.parse
from typing import Literal, Optional

from src.utils.logger import main_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.github.client import GithubClient

from src.l3_agent.skills.registry import SkillResult, skill
from src.l2_interfaces.github.decorators import require_agent_account


class GithubIssues:
    """Skills for working with Issues and comments."""

    def __init__(self, client: GithubClient):
        self.client = client

    @skill()
    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: Optional[Literal["open", "closed", "all"]] = "all",
        per_page: int = 10,
    ) -> SkillResult:
        """
        Returns list of repository issues.
        """

        try:
            params = urllib.parse.urlencode({"state": state, "per_page": per_page})
            data = await self.client.request("GET", f"/repos/{owner}/{repo}/issues?{params}")

            issues = [i for i in data if "pull_request" not in i]
            self.client.state.add_history(f"list_issues: {owner}/{repo} ({state})")

            if not issues:
                return SkillResult.ok(f"No {state} issues in the repository.")

            lines = [f"Issues ({state}) in {owner}/{repo}:"]
            for i in issues:
                user = (i.get("user") or {}).get("login", "Unknown")
                lines.append(
                    f"- #{i.get('number')} | {i.get('title')} | by @{user} | Comments: {i.get('comments')}"
                )

            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Error retrieving issues: {e}")

    @skill()
    async def read_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> SkillResult:
        """
        Reads issue and its comments.
        """

        try:
            # First fetch the issue itself
            issue = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/issues/{issue_number}"
            )

            # Then retrieve comments
            comments = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
            )
            self.client.state.add_history(f"read_issue: {owner}/{repo} #{issue_number}")

            author = (issue.get("user") or {}).get("login", "Unknown")
            body = truncate_text(issue.get("body") or "No description", 2000)

            lines = [
                f"Issue #{issue_number}: {issue.get('title')} (by @{author})",
                f"Description:\n{body}\n---",
            ]

            if comments:
                lines.append("Comments:")
                for c in comments:
                    c_author = (c.get("user") or {}).get("login", "Unknown")
                    c_body = truncate_text(c.get("body") or "", 1000)
                    lines.append(f"[@{c_author}]: {c_body}\n-")
            else:
                lines.append("No comments.")

            main_logger.info(f"[Github] Read Issue #{issue_number} in {owner}/{repo}")
            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Error reading issue: {e}")

    @skill()
    @require_agent_account()
    async def create_issue(
        self, owner: str, repo: str, title: str, body: str = ""
    ) -> SkillResult:
        """
        Creates new issue in repository.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail(
                "Error: To create an Issue, 'agent_account: true' must be enabled in settings and a token added."
            )

        try:
            data = await self.client.request(
                "POST",
                f"/repos/{owner}/{repo}/issues",
                body={"title": title, "body": body},
            )
            issue_num = data.get("number")
            self.client.state.add_history(f"create_issue: {owner}/{repo} #{issue_num}")
            main_logger.info(f"[Github] Created Issue #{issue_num} in {owner}/{repo}")
            return SkillResult.ok(f"True. URL: {data.get('html_url')}")
        except Exception as e:
            return SkillResult.fail(f"Error creating issue: {e}")

    @skill()
    @require_agent_account()
    async def add_comment(
        self, owner: str, repo: str, issue_number: int, body: str
    ) -> SkillResult:
        """
        Adds comment to Issue/Pull Request.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail(
                "Error: To comment, 'agent_account: true' must be enabled."
            )

        try:
            data = await self.client.request(
                "POST",
                f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                body={"body": body},
            )
            self.client.state.add_history(f"add_comment: {owner}/{repo} #{issue_number}")
            main_logger.info(f"[Github] Left comment in #{issue_number} ({owner}/{repo})")
            return SkillResult.ok(f"True. URL: {data.get('html_url')}")
        except Exception as e:
            return SkillResult.fail(f"Error adding comment: {e}")

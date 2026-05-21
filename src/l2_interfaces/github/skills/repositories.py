"""
Skills for working with repositories and code.
"""

import base64
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal

from src.utils.logger import main_logger
from src.utils._tools import truncate_text, validate_sandbox_path, format_size

from src.l2_interfaces.github.client import GithubClient
from src.l2_interfaces.github.decorators import require_agent_account, require_github_token

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class GithubRepositories:
    """Skills for working with repositories and code."""

    def __init__(self, client: GithubClient):
        self.client = client

    @skill(swarm=[Subagents.CODER])
    async def search_repositories(
        self,
        query: str,
        sort: Optional[Literal["stars", "forks", "updated"]],
        per_page: int = 10,
    ) -> SkillResult:
        """
        Searches repositories by keywords or topics.
        """

        try:
            params = {"q": query, "per_page": per_page}
            if sort:
                params["sort"] = sort

            data = await self.client.request("GET", "/search/repositories", params=params)
            self.client.state.add_history(f"search_repos: '{query}'")

            items = data.get("items", [])
            if not items:
                return SkillResult.ok(f"No repositories found for query '{query}'.")

            lines = [
                f"Repositories found: {data.get('total_count')} (showing top {len(items)}):"
            ]
            for item in items:
                repo_name = item.get("full_name")
                stars = item.get("stargazers_count")
                lang = item.get("language") or "N/A"
                desc = item.get("description") or "No description"
                url = item.get("html_url")

                # Protect context against giant descriptions
                clean_desc = truncate_text(desc.replace("\n", " "), 150, "...")

                lines.append(
                    f"- [{repo_name}] ({stars}⭐ | {lang}) - {clean_desc}\n  URL: {url}"
                )

            main_logger.info(f"[Github] Executed repository search: '{query}'")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error during repository search: {e}")

    @skill(swarm=[Subagents.CODER])
    async def get_trending_repositories(
        self,
        period: Optional[Literal["daily", "weekly", "monthly"]],
        language: str = "",
        limit: int = 10,
    ) -> SkillResult:
        """
        Gets trending repositories.

        language: Optional language filter.
        """

        try:
            now = datetime.now(timezone.utc)
            if period == "daily":
                delta = timedelta(days=1)

            elif period == "weekly":
                delta = timedelta(days=7)

            elif period == "monthly":
                delta = timedelta(days=30)

            else:
                return SkillResult.fail(
                    "Error: period must be 'daily', 'weekly', or 'monthly'."
                )

            # Form dork query (repos created during period, sorted by stars)
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
                    "Failed to find trending repositories matching the criteria."
                )

            lang_str = f" for '{language}'" if language else ""
            lines = [f"GitHub Trends ({period}){lang_str}:"]

            for item in items:
                repo_name = item.get("full_name")
                stars = item.get("stargazers_count")
                lang_val = item.get("language") or "N/A"
                desc = item.get("description") or "No description"
                url = item.get("html_url")

                clean_desc = truncate_text(desc.replace("\n", " "), 150, "...")

                lines.append(
                    f"- [{repo_name}] (+{stars}⭐ | {lang_val}) - {clean_desc}\n  URL: {url}"
                )

            main_logger.info(f"[Github] Trends requested: {period}, lang: {language or 'all'}")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error retrieving trends: {e}")

    @skill(swarm=[Subagents.CODER])
    async def get_repo_info(self, owner: str, repo: str) -> SkillResult:
        """
        Returns repository metadata.
        """

        try:
            data = await self.client.request("GET", f"/repos/{owner}/{repo}")
            self.client.state.add_history(f"get_repo: {owner}/{repo}")

            lines = [
                f"Repository: {data.get('full_name')}",
                f"Description: {data.get('description', 'None')}",
                f"Stars: {data.get('stargazers_count')} | Forks: {data.get('forks_count')}",
                f"Language: {data.get('language')} | Branch: {data.get('default_branch')}",
                f"Open issues: {data.get('open_issues_count')}",
            ]
            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Error retrieving repository: {e}")

    @skill()
    @require_github_token()
    async def search_code(self, query: str, per_page: int = 10) -> SkillResult:
        """
        Searches code across GitHub.
        """

        if not self.client.token:
            return SkillResult.fail("Error: Code search requires GITHUB_TOKEN.")

        try:
            params = {"q": query, "per_page": per_page}
            data = await self.client.request("GET", "/search/code", params=params)
            self.client.state.add_history(f"search_code: '{query}'")

            items = data.get("items", [])
            if not items:
                return SkillResult.ok(f"No code found for query '{query}'.")

            lines = [f"Found: {data.get('total_count')} (showing top {len(items)}):"]
            for item in items:
                repo_name = (item.get("repository") or {}).get("full_name")
                lines.append(
                    f"- [{repo_name}] {item.get('path')} (URL: {item.get('html_url')})"
                )

            main_logger.info(f"[Github] Executed code search: '{query}'")
            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Error during code search: {e}")

    @skill(swarm=[Subagents.CODER])
    async def read_file_content(
        self, owner: str, repo: str, path: str, ref: Optional[str] = None
    ) -> SkillResult:
        """
        Reads file content from repository.
        """

        try:
            params = {"ref": ref} if ref else None
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/contents/{path}", params=params
            )

            if isinstance(data, list):
                return SkillResult.fail("Error: Directory path specified instead of file.")

            content_b64 = data.get("content", "")
            content = base64.b64decode(content_b64).decode("utf-8", errors="replace")

            content = truncate_text(content, 10000, "... [File truncated to save context]")

            self.client.state.add_history(f"read_file: {owner}/{repo}:{path}")
            main_logger.info(f"[Github] Read file {path} from {owner}/{repo}")

            return SkillResult.ok(f"Content of {path}:\n```\n{content}\n```")
        except Exception as e:
            return SkillResult.fail(f"Error reading file: {e}")

    @skill(swarm=[Subagents.CODER])
    async def list_recent_commits(
        self, owner: str, repo: str, per_page: int = 10
    ) -> SkillResult:
        """
        Returns repository's recent commits.
        """

        try:
            params = {"per_page": per_page}
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/commits", params=params
            )
            self.client.state.add_history(f"list_commits: {owner}/{repo}")

            if not data:
                return SkillResult.ok("No commits found.")

            lines = [f"Latest commits of {owner}/{repo}:"]
            for c in data:
                sha = (c.get("sha") or "")[:7]
                commit_data = c.get("commit", {})
                msg = commit_data.get("message", "").split("\n")[0]
                author = (commit_data.get("author") or {}).get("name", "Unknown")
                lines.append(f"- [{sha}] {msg} (by {author})")

            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Error retrieving commits: {e}")

    @skill(swarm=[Subagents.CODER])
    async def download_repository(
        self, owner: str, repo: str, dest_filename: str, ref: Optional[str] = None
    ) -> SkillResult:
        """
        Downloads repository as ZIP archive to sandbox/download/.

        ref: Optional branch name, tag, or commit.
        """

        try:
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"sandbox/_system/download/{dest_filename}"

            safe_path = validate_sandbox_path(dest_filename)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            endpoint = f"/repos/{owner}/{repo}/zipball"
            if ref:
                endpoint += f"/{ref}"

            binary_data = await self.client.request("GET", endpoint, response_format="binary")

            if not binary_data:
                return SkillResult.fail(
                    "Failed to download archive (empty response from server)."
                )

            def _save():
                with open(safe_path, "wb") as f:
                    f.write(binary_data)

            await asyncio.to_thread(_save)

            size_str = format_size(safe_path.stat().st_size)
            self.client.state.add_history(f"download_repo: {owner}/{repo}")
            main_logger.info(
                f"[Github] Repository {owner}/{repo} downloaded to {safe_path.name} ({size_str})"
            )

            return SkillResult.ok(
                f"Repository successfully downloaded to archive: sandbox/{safe_path.name} ({size_str})"
            )
        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error downloading repository: {e}")

    @skill(swarm=[Subagents.CODER])
    async def get_commit_details(self, owner: str, repo: str, commit_sha: str) -> SkillResult:
        """
        Returns detailed information about a commit.
        """

        try:
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/commits/{commit_sha}"
            )
            self.client.state.add_history(f"get_commit: {owner}/{repo}@{commit_sha[:7]}")

            commit_msg = data.get("commit", {}).get("message", "No description")
            author = data.get("author", {}).get("login", "Unknown")
            stats = data.get("stats", {})
            files = data.get("files", [])

            lines = [
                f"Commit: {commit_sha}",
                f"Author: @{author}",
                f"Message: {commit_msg}",
                f"Stats: {stats.get('total')} changes (+{stats.get('additions')} / -{stats.get('deletions')})",
                "\nModified files:",
            ]

            if not files:
                lines.append("No modified files.")
            else:
                for f in files:
                    status = f.get("status", "unknown")  # added, modified, removed, renamed
                    filename = f.get("filename", "unknown")
                    adds = f.get("additions", 0)
                    dels = f.get("deletions", 0)
                    lines.append(f"- [{status.upper()}] {filename} (+{adds} / -{dels})")

            main_logger.info(
                f"[Github] Read details of commit {commit_sha[:7]} in {owner}/{repo}"
            )
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error retrieving commit details: {e}")

    @skill(swarm=[Subagents.CODER])
    async def list_repo_directory(
        self, owner: str, repo: str, path: str = "", ref: Optional[str] = None
    ) -> SkillResult:
        """
        Lists directory contents in repository.

        path: Directory path (empty for root).
        ref: Optional branch, tag, or commit.
        """

        try:
            params = {"ref": ref} if ref else None
            # If path is empty, query the root of the repository
            endpoint = (
                f"/repos/{owner}/{repo}/contents/{path.strip('/')}"
                if path
                else f"/repos/{owner}/{repo}/contents"
            )

            data = await self.client.request("GET", endpoint, params=params)
            self.client.state.add_history(f"list_repo_dir: {owner}/{repo}/{path}")

            # If the path points to a file, the API returns a dict instead of a list
            if not isinstance(data, list):
                return SkillResult.fail(
                    "Error: Specified path is a file, not a directory. Use 'read_file_content' skill."
                )

            lines = [f"Contents of /{path} in {owner}/{repo}:"]
            for item in data:
                i_type = "📁 DIR " if item.get("type") == "dir" else "📄 FILE"
                name = item.get("name")
                size = item.get("size", 0)
                size_str = f" ({format_size(size)})" if item.get("type") == "file" else ""
                lines.append(f"- {i_type}: {name}{size_str}")

            main_logger.info(f"[Github] Read directory /{path} in {owner}/{repo}")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error viewing repository directory: {e}")

    @skill()
    @require_agent_account()
    async def star_repository(self, owner: str, repo: str) -> SkillResult:
        """
        Stars repository.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Error: This action requires Agent Account.")

        try:
            await self.client.request("PUT", f"/user/starred/{owner}/{repo}")
            self.client.state.add_history(f"star: {owner}/{repo}")
            main_logger.info(f"[Github] Starred repository {owner}/{repo}")
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Error during starring: {e}")

    @skill()
    @require_agent_account()
    async def unstar_repository(self, owner: str, repo: str) -> SkillResult:
        """
        Unstars repository.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Error: This action requires Agent Account.")

        try:
            await self.client.request("DELETE", f"/user/starred/{owner}/{repo}")
            self.client.state.add_history(f"unstar: {owner}/{repo}")
            main_logger.info(f"[Github] Unstarred repository {owner}/{repo}")
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Error during unstarring: {e}")

    @skill(swarm=[Subagents.CODER])
    async def list_branches(self, owner: str, repo: str, per_page: int = 30) -> SkillResult:
        """
        Returns list of repository branches.
        """

        try:
            params = {"per_page": per_page}
            data = await self.client.request(
                "GET", f"/repos/{owner}/{repo}/branches", params=params
            )
            self.client.state.add_history(f"list_branches: {owner}/{repo}")

            if not data:
                return SkillResult.ok("No branches found.")

            lines = [f"Branches of repository {owner}/{repo}:"]
            for branch in data:
                protected = " (Protected)" if branch.get("protected") else ""
                lines.append(f"- {branch.get('name')}{protected}")

            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Error retrieving branch list: {e}")

    @skill()
    @require_agent_account()
    async def create_repository(
        self, name: str, description: str = "", private: bool = False
    ) -> SkillResult:
        """
        Creates new repository in account.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Error: Creating a repository requires Agent Account.")

        try:
            payload = {
                "name": name,
                "description": description,
                "private": private,
                "auto_init": True,  # Initialize with empty README
            }

            data = await self.client.request("POST", "/user/repos", body=payload)
            self.client.state.add_history(f"create_repo: {name}")

            repo_full_name = data.get("full_name")
            url = data.get("html_url")

            main_logger.info(f"[Github] Created repository {repo_full_name}")
            return SkillResult.ok(f"True. URL: {url}")

        except Exception as e:
            return SkillResult.fail(f"Error creating repository: {e}")

    @skill()
    @require_agent_account()
    async def fork_repository(self, owner: str, repo: str) -> SkillResult:
        """
        Forks repository into account.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Error: Creating a fork requires Agent Account.")

        try:
            data = await self.client.request("POST", f"/repos/{owner}/{repo}/forks")
            self.client.state.add_history(f"fork_repo: {owner}/{repo}")

            fork_name = data.get("full_name")
            url = data.get("html_url")

            main_logger.info(f"[Github] Fork made {owner}/{repo} -> {fork_name}")
            return SkillResult.ok(f"True. URL: {url}")

        except Exception as e:
            return SkillResult.fail(f"Error forking repository: {e}")

    @skill()
    @require_agent_account()
    async def create_gist(
        self, filename: str, content: str, description: str = "", public: bool = True
    ) -> SkillResult:
        """
        Creates public or private Gist snippet.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Error: Creating a Gist requires Agent Account.")

        try:
            payload = {
                "description": description,
                "public": public,
                "files": {filename: {"content": content}},
            }

            data = await self.client.request("POST", "/gists", body=payload)
            self.client.state.add_history("create_gist")

            url = data.get("html_url")
            main_logger.info(f"[Github] Gist created: {filename}")

            return SkillResult.ok(f"Gist successfully created.\nURL: {url}")

        except Exception as e:
            return SkillResult.fail(f"Error creating Gist: {e}")

"""
Agent skills for working with the local Git version control system.

All commands are executed in isolated subprocesses strictly within the `sandbox/` directory.
Includes protection against Argument Injection via the '--' separator.
"""

import asyncio
from pathlib import Path
from typing import Tuple

from src.utils.logger import main_logger
from src.utils._tools import truncate_text, validate_sandbox_path

from src.l2_interfaces.github.client import GithubClient
from src.l2_interfaces.github.decorators import require_github_token

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class GithubLocalGit:
    """Skills for local Git operations (Cloning, Commits, Push) inside the sandbox."""

    def __init__(self, github_client: GithubClient) -> None:
        self.github = github_client

    def _mask_token(self, text: str) -> str:
        """Masks the token in log and console output."""
        if self.github.token:
            return text.replace(self.github.token, "***")
        return text

    async def _run_git_command(self, cwd: Path, *args: str) -> Tuple[int, str, str]:
        """
        Safe execution of git commands in a subprocess.

        Args:
            cwd: Working directory (inside the sandbox).
            args: Git command arguments.

        Returns:
            Tuple: (Return_code, STDOUT, STDERR).
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

            return (
                process.returncode,
                self._mask_token(stdout.decode("utf-8", errors="replace").strip()),
                self._mask_token(stderr.decode("utf-8", errors="replace").strip()),
            )
        except FileNotFoundError:
            raise FileNotFoundError("'git' utility not found on the host system. Install git.")
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise TimeoutError("Git command execution timeout (> 60 sec).")

    @skill(swarm=[Subagents.CODER])
    async def git_clone_repository(
        self, owner: str, repo: str, dest_folder: str
    ) -> SkillResult:
        """
        Clones remote repository to local sandbox preserving .git directory.

        dest_folder: Target folder name inside sandbox/ directory.
        """
        try:
            safe_path = validate_sandbox_path(dest_folder)

            if safe_path.exists() and any(safe_path.iterdir()):
                return SkillResult.fail(
                    f"Error: Directory '{safe_path.name}' already exists and is not empty."
                )

            safe_path.parent.mkdir(parents=True, exist_ok=True)

            if self.github.token:
                repo_url = (
                    f"https://x-access-token:{self.github.token}@github.com/{owner}/{repo}.git"
                )
            else:
                repo_url = f"https://github.com/{owner}/{repo}.git"

            # Pass positional arguments. No '--' separator needed for clone,
            # but we prevent folders named '-o' via validate_sandbox_path checking.
            code, out, err = await self._run_git_command(
                safe_path.parent, "clone", "--", repo_url, safe_path.name
            )

            if code != 0:
                return SkillResult.fail(f"Error during git clone:\n{err or out}")

            await self._run_git_command(safe_path, "config", "user.name", "JAWL Agent")
            await self._run_git_command(safe_path, "config", "user.email", "agent@jawl.local")

            self.github.state.add_history(f"git_clone: {owner}/{repo}")
            main_logger.info(f"[Github] Cloned repository {owner}/{repo} to {safe_path.name}")

            return SkillResult.ok(
                f"Repository successfully cloned to sandbox/{safe_path.name}"
            )

        except FileNotFoundError as e:
            return SkillResult.fail(str(e))
        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error cloning repository: {e}")

    @skill(swarm=[Subagents.CODER])
    async def git_checkout_branch(
        self, repo_folder: str, branch_name: str, create_new: bool = False
    ) -> SkillResult:
        """
        Switches local repository to another branch.

        repo_folder: Sandbox folder with cloned repo.
        create_new: If True, creates new branch.
        """
        try:
            safe_path = validate_sandbox_path(repo_folder)
            if not (safe_path / ".git").exists():
                return SkillResult.fail("Error: Specified folder is not a git repository.")

            # Use '--' to protect against argument injection (-b, --orphan)
            if create_new:
                args = ["checkout", "-b", "--", branch_name]
            else:
                args = ["checkout", "--", branch_name]

            code, out, err = await self._run_git_command(safe_path, *args)

            if code != 0:
                return SkillResult.fail(f"Error during git checkout:\n{err or out}")

            return SkillResult.ok(f"Successfully switched to branch '{branch_name}'.\n{out}")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error during git checkout: {e}")

    @skill(swarm=[Subagents.CODER])
    @require_github_token()
    async def git_commit_and_push(
        self, repo_folder: str, commit_message: str, branch_name: str
    ) -> SkillResult:
        """
        Stages all changes, creates commit, and pushes to origin.

        repo_folder: Sandbox folder with repo.
        """

        if not self.github.token:
            return SkillResult.fail("Error: GITHUB_TOKEN is required to execute 'git push'.")

        try:
            safe_path = validate_sandbox_path(repo_folder)
            if not (safe_path / ".git").exists():
                return SkillResult.fail("Error: Specified folder is not a git repository.")

            code, out, err = await self._run_git_command(safe_path, "add", ".")
            if code != 0:
                return SkillResult.fail(f"Error during git add:\n{err or out}")

            code, status_out, _ = await self._run_git_command(
                safe_path, "status", "--porcelain"
            )
            if not status_out.strip():
                return SkillResult.ok("No changes to commit. Working tree clean.")

            # Message does not require escaping as we pass it as list item,
            # but we explicitly specify -m just in case
            code, out, err = await self._run_git_command(
                safe_path, "commit", "-m", commit_message
            )
            if code != 0:
                return SkillResult.fail(f"Error during git commit:\n{err or out}")

            # Protect branch_name against injection
            code, push_out, push_err = await self._run_git_command(
                safe_path, "push", "-u", "origin", "--", branch_name
            )
            if code != 0:
                return SkillResult.fail(f"Error during git push:\n{push_err or push_out}")

            main_logger.info(
                f"[Github] Committed and pushed to branch {branch_name} (Folder: {safe_path.name})"
            )

            report = truncate_text(push_err or push_out, 500)
            return SkillResult.ok(
                f"Changes successfully committed and pushed to origin/{branch_name}.\n{report}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error during git commit/push: {e}")

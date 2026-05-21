"""
Skills for tracking events in remote or own repositories.
"""

from src.l2_interfaces.github.client import GithubClient
from src.l2_interfaces.github.events import GithubEvents
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class GithubWatchers:
    """Skills for tracking events in remote or own repositories."""

    def __init__(self, client: GithubClient, events: GithubEvents):
        self.client = client
        self.events = events

    @skill()
    async def track_repository(self, owner: str, repo: str) -> SkillResult:
        """
        Starts tracking activity in repository.
        """

        repo_name = f"{owner}/{repo}"

        if repo_name in self.client.state.tracked_repos:
            return SkillResult.ok("True")

        try:
            # Make a test request
            await self.client.request("GET", f"/repos/{owner}/{repo}")

            # Remote subscription (to appear in the Watchers list on the site)
            if self.client.config.agent_account and self.client.token:
                try:
                    await self.client.request(
                        "PUT", f"/repos/{owner}/{repo}/subscription", body={"subscribed": True}
                    )
                except Exception as sub_err:
                    main_logger.debug(
                        f"[Github] Failed to physically subscribe to {repo_name}: {sub_err}"
                    )

            self.client.state.tracked_repos[repo_name] = ""
            self.events.save_persisted_repos()

            main_logger.info(f"[Github] Started tracking repository: {repo_name}")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error adding to tracked (repository not found?): {e}")

    @skill()
    async def untrack_repository(self, owner: str, repo: str) -> SkillResult:
        """
        Stops repository tracking.
        """

        repo_name = f"{owner}/{repo}"

        if repo_name not in self.client.state.tracked_repos:
            return SkillResult.fail(f"Error: Repository {repo_name} was not tracked.")

        del self.client.state.tracked_repos[repo_name]
        self.events.save_persisted_repos()

        # Unsubscribe on the remote site
        if self.client.config.agent_account and self.client.token:
            try:
                await self.client.request("DELETE", f"/repos/{owner}/{repo}/subscription")
            except Exception:
                pass

        main_logger.info(f"[Github] Stopped tracking repository: {repo_name}")
        return SkillResult.ok("True")

    @skill()
    async def get_tracked_repositories(self) -> SkillResult:
        """
        Returns list of tracked repositories.
        """

        tracked = list(self.client.state.tracked_repos.keys())

        if not tracked:
            return SkillResult.ok("List of tracked repositories is empty.")

        return SkillResult.ok("Tracked repositories:\n- " + "\n- ".join(tracked))

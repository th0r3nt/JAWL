"""
Agent skills for working with GitHub profiles and notifications.
"""

from src.utils.logger import main_logger

from src.l2_interfaces.github.client import GithubClient
from src.l2_interfaces.github.decorators import require_agent_account

from src.l3_agent.skills.registry import SkillResult, skill


class GithubAccounts:
    """Skills for working with profiles and notifications."""

    def __init__(self, client: GithubClient) -> None:
        self.client = client

    @skill()
    async def get_user_profile(self, username: str) -> SkillResult:
        """
        Returns public GitHub user profile.
        """

        try:
            data = await self.client.request("GET", f"/users/{username}")
            self.client.state.add_history(f"get_user: {username}")

            if not isinstance(data, dict):
                return SkillResult.fail("Failed to parse profile.")

            lines = [
                f"User: {data.get('login')} ({data.get('name', 'Unnamed')})",
                f"Bio: {data.get('bio', 'None')}",
                f"Public repos: {data.get('public_repos')} | Gists: {data.get('public_gists')}",
                f"Followers: {data.get('followers')} | Following: {data.get('following')}",
                f"Company: {data.get('company', 'None')} | Location: {data.get('location', 'None')}",
            ]
            main_logger.info(f"[Github] Read profile of user {username}")
            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Error retrieving user profile: {e}")

    @skill()
    @require_agent_account()
    async def get_my_notifications(self, unread_only: bool = True) -> SkillResult:
        """
        Checks incoming GitHub notifications.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Error: Checking notifications requires Agent Account.")

        try:
            query = "?all=false" if unread_only else "?all=true"
            data = await self.client.request("GET", f"/notifications{query}")
            self.client.state.add_history("get_notifications")

            if not data or not isinstance(data, list):
                return SkillResult.ok("No new notifications.")

            lines = ["Your latest notifications:"]
            for n in data[:15]:  # Limit to 15
                repo = (n.get("repository") or {}).get("full_name", "Unknown")
                subject = n.get("subject", {})
                title = subject.get("title", "No title")
                n_type = subject.get("type", "Unknown")
                reason = n.get("reason", "unknown")
                lines.append(f"- [{repo}] {n_type}: '{title}' (Reason: {reason})")

            main_logger.info(f"[Github] Checked notifications (Found: {len(data)})")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error checking notifications: {e}")

    @skill()
    @require_agent_account()
    async def mark_notifications_as_read(self) -> SkillResult:
        """
        Marks all current unread notifications as read.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Error: This action requires Agent Account.")

        try:
            # PUT /notifications marks all notifications as read
            await self.client.request("PUT", "/notifications")
            self.client.state.add_history("mark_notifications_read")

            # Instantly clear the dashboard, without waiting for the next poller tick
            self.client.state.unread_notifications = "No new notifications."

            main_logger.info("[Github] All agent notifications marked as read.")
            return SkillResult.ok(
                "All notifications successfully marked as read (inbox cleared)."
            )

        except Exception as e:
            return SkillResult.fail(f"Error marking notifications as read: {e}")

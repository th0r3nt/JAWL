"""
Background GitHub poller.

Monitors notifications (Mentions/Reviews) and activity in tracked repositories (Watchers).
Uses internal event ID cache to bypass 'GitHub Eventual Consistency' issues
(delay of logs appearing in API).
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from src.utils.logger import main_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.dtime import format_datetime

from src.l2_interfaces.github.state import GithubState
from src.l2_interfaces.github.client import GithubClient


class GithubEvents:
    """
    Background GitHub poller (Account Notifications + Watchers).
    """

    def __init__(
        self,
        client: GithubClient,
        state: GithubState,
        event_bus: EventBus,
        data_dir: Path,
        timezone: int = 0,
    ) -> None:
        """
        Initializes the poller.

        Args:
            client: GithubClient instance.
            state: Interface state object.
            event_bus: Global event bus.
            data_dir: Path to local data storage (for Watchers persistence).
            timezone: Timezone offset.
        """
        self.client = client
        self.state = state
        self.bus = event_bus
        self.data_dir = data_dir
        self.timezone = timezone

        self._is_running = False
        self._polling_task: Optional[asyncio.Task] = None

        self._persistence_file = self.data_dir / "interfaces" / "github" / "tracked_repos.json"
        self._persistence_file.parent.mkdir(parents=True, exist_ok=True)

        # Cache of viewed events to bypass GitHub Eventual Consistency issues
        self._seen_event_ids: Dict[str, bool] = {}
        self._initialized_repos: set[str] = set()

    async def start(self) -> None:
        """Starts the background update check cycle."""
        if self._is_running:
            return

        self._load_persisted_repos()
        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        main_logger.info("[Github] Background polling started.")

    async def stop(self) -> None:
        """Stops the update check cycle."""
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        main_logger.info("[Github] Background polling stopped.")

    # ==========================================================
    # PERSISTENCE
    # ==========================================================

    def _load_persisted_repos(self) -> None:
        """Loads the list of tracked repositories from JSON."""
        if not self._persistence_file.exists():
            return
        try:
            with open(self._persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.state.tracked_repos = data
        except Exception as e:
            main_logger.warning(f"[Github] Error reading tracked_repos.json: {e}")

    def save_persisted_repos(self) -> None:
        """Saves the current list of tracked repositories (with watermarks)."""
        try:
            with open(self._persistence_file, "w", encoding="utf-8") as f:
                json.dump(self.state.tracked_repos, f, indent=4)
        except Exception as e:
            main_logger.error(f"[Github] Error saving tracked_repos.json: {e}")

    def _format_gh_time(self, iso_str: str) -> str:
        """Formats ISO time string from GitHub into a readable format."""
        if not iso_str:
            return ""
        try:
            dt = datetime.strptime(iso_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
            return f"[{format_datetime(dt, self.timezone, '%m-%d %H:%M')}] "
        except Exception:
            return ""

    # ==========================================================
    # POLLING LOOP
    # ==========================================================

    async def _loop(self) -> None:
        """Main GitHub API polling loop."""
        while self._is_running:
            try:
                if self.client.config.agent_account and self.client.token:
                    await self._poll_account_state()

                if self.state.tracked_repos:
                    await self._poll_watched_repos()

            except asyncio.CancelledError:
                break
            except Exception as e:
                main_logger.debug(f"[Github] Error in monitoring loop: {e}")

            await asyncio.sleep(self.client.config.polling_interval_sec)

    async def _poll_account_state(self) -> None:
        """Updates the agent profile state and checks unread notifications."""
        try:
            repos_data = await self.client.request(
                "GET", "/user/repos", params={"sort": "updated", "per_page": 5}
            )
            if repos_data and isinstance(repos_data, list):
                repo_lines = []
                for r in repos_data:
                    name = r.get("full_name")
                    stars = r.get("stargazers_count", 0)
                    is_fork = " (Fork)" if r.get("fork") else ""
                    repo_lines.append(f"- {name}{is_fork} ({stars}⭐)")
                self.state.own_repos = (
                    "\n".join(repo_lines)
                    if repo_lines
                    else "You don't have any repositories yet."
                )

            notif_data = await self.client.request(
                "GET", "/notifications", params={"all": "false"}
            )
            if isinstance(notif_data, list):
                count = len(notif_data)
                if count == 0:
                    self.state.unread_notifications = "No new notifications."
                else:
                    notif_lines = [f"You have {count} unread notifications:"]
                    for n in notif_data[:3]:
                        title = n.get("subject", {}).get("title", "No title")
                        repo = (n.get("repository") or {}).get("full_name", "Unknown")
                        n_type = n.get("subject", {}).get("type", "Unknown")
                        time_prefix = self._format_gh_time(n.get("updated_at", ""))
                        notif_lines.append(
                            f"- {time_prefix}[in repo: {repo}] {n_type}: {title}"
                        )
                    self.state.unread_notifications = "\n".join(notif_lines)

        except Exception as e:
            main_logger.debug(f"[Github] Error in background profile update: {e}")

    async def _poll_watched_repos(self) -> None:
        """Monitors the list of tracked repositories and generates system events."""
        modified = False

        for repo_name, last_event_id in list(self.state.tracked_repos.items()):
            try:
                events_data = await self.client.request(
                    "GET", f"/repos/{repo_name}/events", params={"per_page": 30}
                )

                if not isinstance(events_data, list) or not events_data:
                    continue

                events_data.reverse()  # Chronological order: old to new

                is_first_poll = repo_name not in self._initialized_repos
                self._initialized_repos.add(repo_name)

                highest_parsed_id = last_event_id

                for event in events_data:
                    event_id = str(event.get("id"))
                    if not event_id or event_id in self._seen_event_ids:
                        continue

                    # Mark as viewed
                    self._seen_event_ids[event_id] = True

                    # Memory leak protection
                    if len(self._seen_event_ids) > 1000:
                        for k in list(self._seen_event_ids.keys())[:500]:
                            del self._seen_event_ids[k]

                    parsed_msg = self._parse_github_event(event)

                    if not parsed_msg:
                        continue

                    # Determine if we need to trigger the system
                    is_new = False
                    if not last_event_id:
                        # Just started tracking the repository - populate quietly
                        is_new = False

                    elif is_first_poll:
                        # Agent restart. Publish only those that are objectively greater than the last saved ID
                        try:
                            is_new = int(event_id) > int(last_event_id)
                        except (ValueError, TypeError):
                            is_new = event_id > str(last_event_id)

                    else:
                        # Runtime. Since we haven't seen it yet (passed the seen_event_ids check) - it means it's new.
                        # This resolves the GitHub Eventual Consistency issue (when PushEvent arrives with a delay)
                        is_new = True

                    self.state.add_watcher_event(parsed_msg)

                    if is_new:
                        await self.bus.publish(
                            Events.GITHUB_REPO_ACTIVITY, repo=repo_name, message=parsed_msg
                        )

                    # Update the ID watermark to save to disk
                    try:
                        if (
                            int(event_id) > int(highest_parsed_id)
                            if highest_parsed_id
                            else True
                        ):
                            highest_parsed_id = event_id
                    except (ValueError, TypeError):
                        highest_parsed_id = event_id

                if highest_parsed_id != last_event_id:
                    self.state.tracked_repos[repo_name] = highest_parsed_id
                    modified = True

            except Exception as e:
                main_logger.debug(f"[Github] Error polling repository {repo_name}: {e}")

        if modified:
            self.save_persisted_repos()

    def _parse_github_event(self, event: dict) -> Optional[str]:
        """Parses raw GitHub event into a human-readable string."""
        event_type = event.get("type")
        actor = event.get("actor", {}).get("login", "Unknown")
        repo = event.get("repo", {}).get("name", "Unknown")
        payload = event.get("payload", {})
        time_prefix = self._format_gh_time(event.get("created_at", ""))

        if event_type == "PushEvent":
            commits = payload.get("commits", [])
            count = payload.get("size", len(commits))
            branch = payload.get("ref", "").replace("refs/heads/", "")

            if count == 0:
                return None

            msg = commits[0].get("message", "").split("\n")[0] if commits else "No description"
            branch_str = f" to branch {branch}" if branch else ""
            return f"{time_prefix}[in repo: {repo}] @{actor} pushed {count} commit(s){branch_str}. Last: '{msg}'"

        elif event_type == "IssuesEvent":
            action = payload.get("action")
            if action not in ("opened", "closed", "reopened", "commented"):
                return None
            issue_num = payload.get("issue", {}).get("number", "?")
            title = payload.get("issue", {}).get("title", "")
            return f"{time_prefix}[in repo: {repo}] @{actor} {action} issue #{issue_num}: '{title}'"

        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr_obj = payload.get("pull_request", {})
            pr_num = pr_obj.get("number", "?")
            title = pr_obj.get("title", "").strip()

            if action == "closed":
                action = "merged" if pr_obj.get("merged") else "closed (without merge)"

            title_str = f": '{title}'" if title else ""
            return f"{time_prefix}[in repo: {repo}] @{actor} {action} Pull Request #{pr_num}{title_str}"

        elif event_type == "IssueCommentEvent":
            action = payload.get("action")
            if action != "created":
                return None
            issue_num = payload.get("issue", {}).get("number", "?")
            return f"{time_prefix}[in repo: {repo}] @{actor} {action} comment on Issue/PR #{issue_num}"

        elif event_type == "ReleaseEvent":
            action = payload.get("action")
            tag = payload.get("release", {}).get("tag_name", "?")
            return f"{time_prefix}[in repo: {repo}] @{actor} {action} release {tag}"

        return None

"""
L0 State for the GitHub interface.

Stores connection status, active repositories, notifications, and history of queries.
"""


class GithubState:
    """
    Stores the state of the GitHub client.
    Holds is_online flag, agent account info, repositories,
    notifications, and a short query history.
    """

    def __init__(self, history_limit: int = 10):
        self.is_online = False
        self.history_limit = history_limit
        self.history: list[str] = []

        self.account_info = "Awaiting initialization..."
        self.own_repos = "Repositories unknown."
        self.unread_notifications = "No notifications."

        # Watchers: { "owner/repo": "last_event_id" }
        self.tracked_repos: dict[str, str] = {}

        # MRU cache of the latest events to inject into the agent's context
        self.recent_watcher_events: list[str] = []

    def add_history(self, entry: str) -> None:
        """Adds an entry to the beginning of the history (newest on top)."""
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    def add_watcher_event(self, event_str: str) -> None:
        """Adds a repository event to the context."""
        self.recent_watcher_events.insert(0, event_str)
        if len(self.recent_watcher_events) > 10:  # Keep last 10 events
            self.recent_watcher_events.pop()

    @property
    def github_history(self) -> str:
        if not self.history:
            return "History is empty."
        return "\n".join(f"- {item}" for item in self.history)

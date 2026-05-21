"""
L0 State for the Web HTTP interface.

Stores connection status and history of raw HTTP requests.
"""


class WebHTTPState:
    """Stores the state of the agent's raw HTTP queries."""

    def __init__(self, history_limit: int = 10):
        self.is_online = False
        self.history_limit = history_limit
        self.history: list[str] = []

    def add_history(self, entry: str):
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def http_history(self) -> str:
        if not self.history:
            return "History is empty."
        return "\n".join(f"- {item}" for item in self.history)
"""
L0 State for the Edge TTS interface.

Stores generation history and the cache of available Microsoft Edge voices.
"""


class CloudEdgeTTSState:
    """
    Microsoft Edge TTS client dashboard.
    """

    def __init__(self, history_limit: int = 5) -> None:
        self.is_online: bool = False
        self.history_limit: int = history_limit

        # Cached voice names (to display in the prompt and prevent frequent API calls)
        self.available_voices_cache: list[str] = []

        # MRU cache of generation history
        self.history: list[str] = []

    def add_history(self, entry: str) -> None:
        """
        Adds a record of successful generation to the beginning of the list.
        Truncates the list when the limit is exceeded.
        """
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def recent_history(self) -> str:
        """Formats the history for injection into the agent's Markdown context."""
        if not self.history:
            return "No files were generated."
        return "\n".join(f"- {item}" for item in self.history)

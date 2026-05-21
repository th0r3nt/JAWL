"""
L0 State for the Cloud Whisper STT interface.

Stores connection status and the MRU-cache (history) of the last transcribed audio files
to ensure the agent does not lose context of its actions.
"""


class CloudWhisperSTTState:
    """
    Cloud Whisper STT client dashboard.
    """

    def __init__(self, history_limit: int = 5) -> None:
        self.is_online: bool = False
        self.history_limit: int = history_limit

        # MRU cache of the latest transcriptions
        self.history: list[str] = []

    def add_history(self, entry: str) -> None:
        """
        Adds a record of successful transcription to the beginning of the list.
        Truncates the list when the limit is exceeded.
        """
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def recent_history(self) -> str:
        """Formats the history for injection into the agent's Markdown context."""
        if not self.history:
            return "Audio files were not transcribed."
        return "\n".join(f"- {item}" for item in self.history)

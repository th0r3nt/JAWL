"""
L0 State for the ElevenLabs TTS interface.

Stores quota limits and the cache of recently generated audio files.
"""


class CloudElevenLabsTTSState:
    """
    TTS client dashboard.
    """

    def __init__(self, history_limit: int = 5):
        self.is_online = False
        self.history_limit = history_limit

        # Quotas (characters)
        self.character_count = 0
        self.character_limit = 0

        # Cached voice names
        self.available_voices_cache: list[str] = []

        self.history: list[str] = []

    def add_history(self, entry: str) -> None:
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def recent_history(self) -> str:
        if not self.history:
            return "No files were generated."
        return "\n".join(f"- {item}" for item in self.history)

"""
L0 State for the Host Terminal interface.

Stores connection status, UI connection state, and the recent messages cache.
"""


class HostTerminalState:
    """
    Stores the state of the local terminal (CLI chat) and the history of recent messages.
    """

    def __init__(self, context_limit: int = 15):
        self.is_online = False
        self.is_ui_connected = False
        self.context_limit = context_limit

        # MRU list of strings
        self.recent_messages: list[str] = []

    def add_message(self, sender: str, text: str, time_str: str = ""):
        """Adds a message to the end and shifts the cache if the limit is exceeded."""
        prefix = f"[{time_str}] " if time_str else ""
        self.recent_messages.append(f"{prefix}[{sender}]: {text}")
        if len(self.recent_messages) > self.context_limit:
            self.recent_messages.pop(0)

    @property
    def formatted_messages(self) -> str:
        if not self.recent_messages:
            return "Message history is empty."
        return "\n".join(self.recent_messages)

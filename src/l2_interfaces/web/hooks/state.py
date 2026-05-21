"""
L0 State for the Web Hooks interface.

Stores incoming webhook requests history and server configuration.
"""


class WebHooksState:
    """Stores the state of the webhook server and history of the latest incoming data."""

    def __init__(self, history_limit: int = 20):
        self.is_online = False
        self.host = "127.0.0.1"
        self.port = 8080

        self.history_limit = history_limit
        self.recent_hooks: list[dict] = []  # Stores full data for the read skill
        self.preview_lines: list[str] = []  # Stores only truncated text for the prompt

    def add_hook(
        self, hook_id: str, source: str, time_str: str, payload: dict | str, preview: str
    ):
        self.recent_hooks.insert(
            0, {"id": hook_id, "source": source, "time": time_str, "payload": payload}
        )
        self.preview_lines.insert(
            0, f"- [ID: `{hook_id}`] {time_str} | From: {source} | Data: {preview}"
        )

        if len(self.recent_hooks) > self.history_limit:
            self.recent_hooks.pop()
            self.preview_lines.pop()

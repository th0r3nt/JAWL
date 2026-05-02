class WebHooksState:
    """
    Хранит состояние сервера вебхуков и историю последних входящих данных.
    """

    def __init__(self, history_limit: int = 20):
        self.is_online = False
        self.host = "127.0.0.1"
        self.port = 8080

        self.history_limit = history_limit
        self.recent_hooks: list[dict] = []  # Хранит полные данные для навыка чтения
        self.preview_lines: list[str] = []  # Хранит только обрезанный текст для промпта

    def add_hook(self, hook_id: str, source: str, time_str: str, payload: dict | str, preview: str):
        self.recent_hooks.insert(0, {"id": hook_id, "source": source, "time": time_str, "payload": payload})
        self.preview_lines.insert(0, f"- [ID: `{hook_id}`] {time_str} | От: {source} | Данные: {preview}")

        if len(self.recent_hooks) > self.history_limit:
            self.recent_hooks.pop()
            self.preview_lines.pop()
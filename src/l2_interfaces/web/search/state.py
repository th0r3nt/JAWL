class WebSearchState:
    """
    Хранит историю веб-серфинга агента (Search / Deep Research).
    """

    def __init__(self, history_limit: int = 10):
        self.is_online = False
        self.history_limit = history_limit
        self.history: list[str] = []

    def add_history(self, entry: str):
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def browser_history(self) -> str:
        if not self.history:
            return "История пуста."
        return "\n".join(f"- {item}" for item in self.history)

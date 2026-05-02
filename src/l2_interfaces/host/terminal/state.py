class HostTerminalState:
    """
    Хранит состояние локального терминала (CLI-чата) и историю последних сообщений.
    """

    def __init__(self, context_limit: int = 15):
        self.is_online = False
        self.is_ui_connected = False
        self.context_limit = context_limit

        # Храним список строк для удобства сдвига (MRU)
        self.recent_messages: list[str] = []

    def add_message(self, sender: str, text: str, time_str: str = ""):
        """Добавляет сообщение в конец и сдвигает кэш, если превышен лимит."""
        prefix = f"[{time_str}] " if time_str else ""
        self.recent_messages.append(f"{prefix}[{sender}]: {text}")
        if len(self.recent_messages) > self.context_limit:
            self.recent_messages.pop(0)

    @property
    def formatted_messages(self) -> str:
        if not self.recent_messages:
            return "История сообщений пуста."
        return "\n".join(self.recent_messages)

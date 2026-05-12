"""
L0 State для интерфейса Cloud Whisper STT.

Хранит статус подключения и MRU-кэш (историю) последних транскрибированных аудиофайлов,
чтобы агент не терял контекст своих действий.
"""


class CloudWhisperSTTState:
    """
    Приборная панель клиента Cloud Whisper STT.
    """

    def __init__(self, history_limit: int = 5) -> None:
        self.is_online: bool = False
        self.history_limit: int = history_limit

        # MRU-кэш истории транскрибаций
        self.history: list[str] = []

    def add_history(self, entry: str) -> None:
        """
        Добавляет запись об успешной транскрибации в начало списка.
        Обрезает список при превышении лимита.
        """
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def recent_history(self) -> str:
        """Форматирует историю для вставки в Markdown-контекст агента."""
        if not self.history:
            return "Аудиофайлы не транскрибировались."
        return "\n".join(f"- {item}" for item in self.history)

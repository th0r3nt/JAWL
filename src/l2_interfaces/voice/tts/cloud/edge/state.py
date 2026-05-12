"""
L0 State для интерфейса Edge TTS.

Хранит информацию об истории генерации и кэш доступных голосов Microsoft Edge.
"""


class CloudEdgeTTSState:
    """
    Приборная панель TTS-клиента Microsoft Edge.
    """

    def __init__(self, history_limit: int = 5) -> None:
        self.is_online: bool = False
        self.history_limit: int = history_limit

        # Кэшированные имена голосов (для отображения в промпте и защиты от частых API-вызовов)
        self.available_voices_cache: list[str] = []

        # MRU-кэш истории генераций
        self.history: list[str] = []

    def add_history(self, entry: str) -> None:
        """
        Добавляет запись об успешной генерации в начало списка.
        Обрезает список при превышении лимита.
        """
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def recent_history(self) -> str:
        """Форматирует историю для вставки в Markdown-контекст агента."""
        if not self.history:
            return "Файлы не генерировались."
        return "\n".join(f"- {item}" for item in self.history)

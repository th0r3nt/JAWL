"""
L0 State для интерфейса ElevenLabs TTS.
Хранит информацию о лимитах и кэш последних сгенерированных аудио.
"""


class CloudElevenLabsTTSState:
    """
    Приборная панель TTS-клиента.
    """

    def __init__(self, history_limit: int = 5):
        self.is_online = False
        self.history_limit = history_limit

        # Квоты (символы)
        self.character_count = 0
        self.character_limit = 0

        # Кэшированные имена голосов
        self.available_voices_cache: list[str] = []

        self.history: list[str] = []

    def add_history(self, entry: str) -> None:
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def recent_history(self) -> str:
        if not self.history:
            return "Файлы не генерировались."
        return "\n".join(f"- {item}" for item in self.history)

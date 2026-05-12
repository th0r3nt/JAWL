"""
Утилита конфигурации и параметров для голосов Edge TTS.
"""

from src.utils.settings import EdgeConfig


class EdgeVoiceManager:
    """Хранилище настроек голоса Microsoft Edge."""

    def __init__(self, config: EdgeConfig) -> None:
        self.main_voice = config.main_voice
        self.allowed_voices = config.available_voices
        self.rate = config.rate
        self.volume = config.volume
        self.pitch = config.pitch

"""
Хранилище конфигураций и параметров для голосов ElevenLabs.
Изолирует настройки генерации от HTTP клиента.
"""

from src.utils.settings import ElevenLabsConfig


class VoiceManager:
    """Утилита для работы с настройками голосов и моделей."""

    def __init__(self, config: ElevenLabsConfig):
        self.model_id = config.tts_model
        self.main_voice = config.main_voice
        self.allowed_voices = config.available_voices
        self.stability = config.stability
        self.similarity_boost = config.similarity_boost

    def get_voice_settings(self) -> dict:
        """Возвращает параметры генерации для API."""
        return {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
        }

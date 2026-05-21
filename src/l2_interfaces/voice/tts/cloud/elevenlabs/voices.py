"""
Configuration and parameter storage for ElevenLabs voices.

Isolates generation settings from the HTTP client.
"""

from src.utils.settings import ElevenLabsConfig


class VoiceManager:
    """Utility for working with voice and model settings."""

    def __init__(self, config: ElevenLabsConfig):
        self.model_id = config.tts_model
        self.main_voice = config.main_voice
        self.allowed_voices = config.available_voices
        self.stability = config.stability
        self.similarity_boost = config.similarity_boost

    def get_voice_settings(self) -> dict:
        """Returns generation parameters for the API."""
        return {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
        }

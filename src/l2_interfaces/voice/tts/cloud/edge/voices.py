"""
Configuration utility and parameters for Edge TTS voices.
"""

from src.utils.settings import EdgeConfig


class EdgeVoiceManager:
    """Microsoft Edge voice settings storage."""

    def __init__(self, config: EdgeConfig) -> None:
        self.main_voice = config.main_voice
        self.allowed_voices = config.available_voices
        self.rate = config.rate
        self.volume = config.volume
        self.pitch = config.pitch

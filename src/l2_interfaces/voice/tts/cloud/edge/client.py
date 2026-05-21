"""
Stateful client for working with Microsoft Edge TTS.

Provides voice list caching on system startup and
performs asynchronous audio file generation without blocking the Event Loop.
"""

import edge_tts
from typing import Any

from src.utils.logger import main_logger
from src.l2_interfaces.voice.tts.cloud.edge.state import CloudEdgeTTSState
from src.l2_interfaces.voice.tts.cloud.edge.voices import EdgeVoiceManager


class EdgeClient:
    """Connection and generation manager for Edge TTS."""

    def __init__(self, state: CloudEdgeTTSState, voice_manager: EdgeVoiceManager) -> None:
        """
        Initializes the client.

        Args:
            state: L0 state.
            voice_manager: Default voice settings.
        """

        self.state = state
        self.voice_manager = voice_manager

    async def start(self) -> None:
        """
        Lifecycle method.
        Loads the Microsoft Edge voice cache if the library is installed.
        """

        try:
            voices = await edge_tts.list_voices()
            for v in voices:
                short_name = v.get("ShortName", "")
                # If a list is strictly specified in config - filter, otherwise take everything
                if (
                    not self.voice_manager.allowed_voices
                    or short_name in self.voice_manager.allowed_voices
                ):
                    locale = v.get("Locale", "Unknown")
                    gender = v.get("Gender", "Unknown")
                    self.state.available_voices_cache.append(
                        f"{short_name} ({locale}, {gender})"
                    )

            self.state.is_online = True
            main_logger.info("[Edge TTS] Interface started. Voice cache loaded.")

        except Exception as e:
            main_logger.error(f"[Edge TTS] Error initializing voice list: {e}")
            self.state.is_online = False

    async def stop(self) -> None:
        """
        Correctly stops the interface.
        """

        self.state.is_online = False

    async def generate_audio(self, text: str, voice: str, output_path: str) -> None:
        """
        Asynchronously generates and saves the audio file.

        Args:
            text: Text for voiceover.
            voice: Edge voice ShortName.
            output_path: Absolute path to save the .mp3 file.
        """

        # Pass generation parameters (rate, volume, pitch)
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=self.voice_manager.rate,
            volume=self.voice_manager.volume,
            pitch=self.voice_manager.pitch,
        )
        await communicate.save(output_path)

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Formats the state block for the agent system prompt.
        """

        desc = "Description: TTS generation via Microsoft Edge API."

        if not self.state.is_online:
            return f"### EDGE TTS [OFF]\n{desc}\nThe interface is disabled."

        main_voice_str = self.voice_manager.main_voice

        # Format available voices list (limit output to preserve context tokens)
        voices_cache = self.state.available_voices_cache
        if not voices_cache:
            available_str = "  Cache is empty."
        elif len(voices_cache) > 10:
            display_voices = voices_cache[:10]
            available_str = "\n".join(f"  - {v}" for v in display_voices)
            available_str += f"\n  ...and {len(voices_cache) - 10} more voices hidden."
        else:
            available_str = "\n".join(f"  - {v}" for v in voices_cache)

        return f"""### EDGE TTS [ON]
{desc}

* Main voice (default): {main_voice_str}
* Available voices:
{available_str}

* Generation history:
{self.state.recent_history}
"""

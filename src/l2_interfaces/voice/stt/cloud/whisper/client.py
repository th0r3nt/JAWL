"""
Stateful client for working with OpenAI Whisper API (and compatible ones).

Manages HTTP sessions pool via the openai library and encapsulates
the logic of sending binary audio data to the server.
"""

from typing import Any, Optional, Tuple
from openai import AsyncOpenAI

from src.utils.logger import main_logger
from src.utils.settings import CloudWhisperConfig
from src.l2_interfaces.voice.stt.cloud.whisper.state import CloudWhisperSTTState


class CloudWhisperSTTClient:
    """Cloud Whisper STT connection manager."""

    def __init__(
        self,
        state: CloudWhisperSTTState,
        config: CloudWhisperConfig,
        api_key: str,
        api_url: Optional[str] = None,
    ) -> None:
        """
        Initializes the client.

        Args:
            state: L0 state (dashboard).
            config: Interface configuration from YAML.
            api_key: API key.
            api_url: Optional custom URL (e.g., for Groq or local vLLM).
        """

        self.state = state
        self.config = config
        self.api_key = api_key
        self.api_url = api_url

        self._client: Optional[AsyncOpenAI] = None

    async def start(self) -> None:
        """
        Initializes the OpenAI HTTP client.
        """
        try:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_url if self.api_url else None,
                timeout=self.config.timeout_sec,
            )
            self.state.is_online = True
            main_logger.info("[Cloud Whisper STT] Interface started.")

        except Exception as e:
            main_logger.error(f"[Cloud Whisper STT] Client initialization error: {e}")
            self.state.is_online = False

    async def stop(self) -> None:
        """
        Correctly closes the HTTP session.
        """
        if self._client:
            await self._client.close()
        self.state.is_online = False

    async def transcribe(self, file_tuple: Tuple[str, bytes]) -> str:
        """
        Sends audio file to API for transcription.

        Args:
            file_tuple: Tuple (filename, file_bytes). Format required by OpenAI SDK.

        Returns:
            Transcribed text (str).

        Raises:
            RuntimeError: If client is not started.
            Exception: On network or API errors.
        """

        if not self._client:
            raise RuntimeError("Whisper client is not initialized.")

        response = await self._client.audio.transcriptions.create(
            model=self.config.model,
            file=file_tuple,
            temperature=self.config.temperature,
        )
        return response.text

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Formats the state block for the agent system prompt.
        """
        desc = "Description: STT transcription via OpenAI Whisper."

        if not self.state.is_online:
            return f"### CLOUD WHISPER STT [OFF]\n{desc}\nThe interface is disabled."

        url_str = self.api_url if self.api_url else "OpenAI Official"

        return f"""### CLOUD WHISPER STT [ON]
{desc}
* Provider: {url_str}
* Model: {self.config.model}

* Transcription History:
{self.state.recent_history}
"""

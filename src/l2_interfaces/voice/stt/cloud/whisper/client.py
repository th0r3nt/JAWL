"""
Stateful-клиент для работы с OpenAI Whisper API (и совместимыми).

Управляет пулом HTTP-сессий через библиотеку opena` и инкапсулирует
логику отправки бинарных аудио-данных на сервер.
"""

from typing import Any, Optional, Tuple
from openai import AsyncOpenAI

from src.utils.logger import main_logger
from src.utils.settings import CloudWhisperConfig
from src.l2_interfaces.voice.stt.cloud.whisper.state import CloudWhisperSTTState


class CloudWhisperSTTClient:
    """Менеджер соединений Cloud Whisper STT."""

    def __init__(
        self,
        state: CloudWhisperSTTState,
        config: CloudWhisperConfig,
        api_key: str,
        api_url: Optional[str] = None,
    ) -> None:
        """
        Инициализирует клиент.

        Args:
            state: L0 стейт (приборная панель).
            config: Конфигурация интерфейса из YAML.
            api_key: Ключ API.
            api_url: Опциональный кастомный URL (например, для Groq или локального vLLM).
        """

        self.state = state
        self.config = config
        self.api_key = api_key
        self.api_url = api_url

        self._client: Optional[AsyncOpenAI] = None

    async def start(self) -> None:
        """
        Инициализирует HTTP-клиент OpenAI.
        """
        try:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_url if self.api_url else None,
                timeout=self.config.timeout_sec,
            )
            self.state.is_online = True
            main_logger.info("[Cloud Whisper STT] Интерфейс запущен.")

        except Exception as e:
            main_logger.error(f"[Cloud Whisper STT] Ошибка инициализации клиента: {e}")
            self.state.is_online = False

    async def stop(self) -> None:
        """
        Штатно закрывает HTTP-сессию.
        """
        if self._client:
            await self._client.close()
        self.state.is_online = False

    async def transcribe(self, file_tuple: Tuple[str, bytes]) -> str:
        """
        Отправляет аудиофайл в API для транскрибации.

        Args:
            file_tuple: Кортеж (имя_файла, байты_файла). Формат, требуемый SDK OpenAI.

        Returns:
            Распознанный текст (str).

        Raises:
            RuntimeError: Если клиент не запущен.
            Exception: При ошибках сети или API.
        """

        if not self._client:
            raise RuntimeError("Клиент Whisper не инициализирован.")

        response = await self._client.audio.transcriptions.create(
            model=self.config.model,
            file=file_tuple,
            temperature=self.config.temperature,
        )
        return response.text

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Формирует блок состояния для системного промпта агента.
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
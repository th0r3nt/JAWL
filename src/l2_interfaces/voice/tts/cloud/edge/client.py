"""
Stateful-клиент для работы с Microsoft Edge TTS.

Обеспечивает кэширование списка голосов при старте системы и
выполняет асинхронную генерацию аудиофайлов без блокировки Event Loop.
"""

import edge_tts
from typing import Any

from src.utils.logger import main_logger
from src.l2_interfaces.voice.tts.cloud.edge.state import CloudEdgeTTSState
from src.l2_interfaces.voice.tts.cloud.edge.voices import EdgeVoiceManager


class EdgeClient:
    """Менеджер соединений и генерации Edge TTS."""

    def __init__(self, state: CloudEdgeTTSState, voice_manager: EdgeVoiceManager) -> None:
        """
        Инициализирует клиент.

        Args:
            state: L0 стейт.
            voice_manager: Настройки голосов по умолчанию.
        """

        self.state = state
        self.voice_manager = voice_manager

    async def start(self) -> None:
        """
        Метод жизненного цикла.
        Загружает кэш голосов Microsoft Edge, если библиотека установлена.
        """

        try:
            voices = await edge_tts.list_voices()
            for v in voices:
                short_name = v.get("ShortName", "")
                # Если в конфиге жестко задан список - фильтруем, иначе берем всё
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
            main_logger.info("[Edge TTS] Интерфейс запущен. Кэш голосов загружен.")

        except Exception as e:
            main_logger.error(f"[Edge TTS] Ошибка инициализации списка голосов: {e}")
            self.state.is_online = False

    async def stop(self) -> None:
        """
        Штатно останавливает интерфейс.
        """

        self.state.is_online = False

    async def generate_audio(self, text: str, voice: str, output_path: str) -> None:
        """
        Асинхронно генерирует и сохраняет аудиофайл.

        Args:
            text: Текст для озвучки.
            voice: ShortName голоса Edge.
            output_path: Абсолютный путь для сохранения .mp3 файла.
        """

        # Передаем параметры генерации (скорость, громкость, питч)
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
        Формирует блок состояния для системного промпта агента.
        """

        if not self.state.is_online:
            return "### EDGE TTS [OFF]\nThe interface is disabled."

        main_voice_str = self.voice_manager.main_voice

        # Формируем список доступных голосов (лимитируем вывод, чтобы не выжечь токены)
        voices_cache = self.state.available_voices_cache
        if not voices_cache:
            available_str = "  Кэш пуст."
        elif len(voices_cache) > 10:
            display_voices = voices_cache[:10]
            available_str = "\n".join(f"  - {v}" for v in display_voices)
            available_str += f"\n  ...и еще {len(voices_cache) - 10} голосов скрыто."
        else:
            available_str = "\n".join(f"  - {v}" for v in voices_cache)

        return f"""### EDGE TTS [ON]
* Провайдер: Microsoft Edge Cloud TTS

* Основной голос (по умолчанию): {main_voice_str}
* Доступные голоса:
{available_str}

* История генераций:
{self.state.recent_history}
"""

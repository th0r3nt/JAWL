"""
Навыки агента для синтеза речи через Microsoft Edge TTS.
"""

import uuid
from typing import Optional

from src.utils._tools import format_size
from src.utils.logger import main_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l2_interfaces.voice.tts.cloud.edge.client import EdgeClient
from src.l2_interfaces.host.os.client import HostOSClient


class EdgeTTSGeneration:
    """Инструменты генерации речи Edge TTS."""

    def __init__(self, client: EdgeClient, host_os: HostOSClient) -> None:
        """
        Args:
            client: Клиент Edge TTS.
            host_os: Гейткипер для безопасного резолва путей сохранения.
        """

        self.client = client
        self.host_os = host_os

    @skill(swarm=[Subagents.CODER, Subagents.WEB_RESEARCHER])
    async def get_available_voices(self) -> SkillResult:
        """
        Returns available voices.
        """

        voices = self.client.state.available_voices_cache
        if not voices:
            return SkillResult.fail(
                "Кэш голосов пуст. Возможно, отсутствует подключение к сети или интерфейс оффлайн."
            )

        return SkillResult.ok("Доступные голоса Edge TTS:\n- " + "\n- ".join(voices))

    @skill()
    async def generate_speech(
        self, text: str, voice_id: Optional[str] = None, filename: Optional[str] = None
    ) -> SkillResult:
        """
        Synthesizes and saves speech. 
        
        filename: Output .mp3 name.
        """

        if not text.strip():
            return SkillResult.fail("Текст для озвучки не может быть пустым.")

        v_id = voice_id if voice_id else self.client.voice_manager.main_voice
        f_name = filename if filename else f"edge_speech_{uuid.uuid4().hex[:8]}.mp3"

        # Направляем по умолчанию в системную папку загрузок песочницы
        if "/" not in f_name and "\\" not in f_name:
            f_name = f"sandbox/_system/download/{f_name}"

        try:
            # Безопасно резолвим путь через гейткипер
            safe_path = self.host_os.validate_path(f_name, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            main_logger.info(
                f"[Edge TTS] Генерация речи начата (Голос: {v_id}, Файл: {safe_path.name})"
            )

            # Вызываем асинхронную генерацию
            await self.client.generate_audio(text=text, voice=v_id, output_path=str(safe_path))

            # Форматируем логи
            size_str = format_size(safe_path.stat().st_size)
            rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()

            self.client.state.add_history(f"Сгенерирован {rel_path} (size: {size_str}, text: {text})")

            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        
        except RuntimeError as e:
            return SkillResult.fail(str(e))
        
        except Exception as e:
            main_logger.error(f"[Edge TTS] Ошибка генерации: {e}")
            return SkillResult.fail(f"Ошибка API генерации речи (Edge): {e}")

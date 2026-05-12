"""
Навыки агента для транскрибации (Speech-to-Text).

Позволяют распознавать речь из локальных медиа-файлов, лежащих в песочнице.
Включают защиту файловых путей и лимиты на длину возвращаемого текста.
"""

import asyncio

from src.utils.logger import main_logger
from src.utils._tools import format_size, truncate_text
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.voice.stt.cloud.whisper.client import CloudWhisperSTTClient


class CloudWhisperSTTTranscribation:
    """Инструменты для перевода аудио/видео в текст."""

    # Поддерживаемые OpenAI Whisper форматы
    ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}

    def __init__(self, client: CloudWhisperSTTClient, host_os: HostOSClient) -> None:
        """
        Args:
            client: Клиент API Whisper.
            host_os: Гейткипер ОС для безопасного резолва путей к файлам.
        """
        self.client = client
        self.host_os = host_os

    @skill(swarm=[Subagents.WEB_RESEARCHER, Subagents.CODER])
    async def transcribe_audio(self, filepath: str) -> SkillResult:
        """
        Извлекает и распознает речь из медиафайла.

        filepath: Относительный путь к файлу внутри папки `sandbox/`.
        """
        try:
            # 1. Валидируем путь через гейткипер
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл не найден ({safe_path.name}).")

            ext = safe_path.suffix.lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                return SkillResult.fail(
                    f"Ошибка: Расширение '{ext}' не поддерживается. Разрешены: {', '.join(self.ALLOWED_EXTENSIONS)}"
                )

            size_bytes = safe_path.stat().st_size
            if size_bytes == 0:
                return SkillResult.fail("Ошибка: Файл пуст.")

            # API OpenAI имеет лимит 25 МБ
            if size_bytes > 25 * 1024 * 1024:
                return SkillResult.fail(
                    f"Ошибка: Размер файла ({format_size(size_bytes)}) превышает лимит API (25 MB)."
                )

            main_logger.info(
                f"[Cloud Whisper STT] Начинаю транскрибацию: {safe_path.name} ({format_size(size_bytes)})..."
            )

            # 2. Асинхронно читаем байты с диска
            def _read_bytes() -> bytes:
                with open(safe_path, "rb") as f:
                    return f.read()

            file_bytes = await asyncio.to_thread(_read_bytes)
            file_tuple = (safe_path.name, file_bytes)

            # 3. Отправляем в API
            text = await self.client.transcribe(file_tuple)

            if not text.strip():
                return SkillResult.ok(
                    "В файле не обнаружено распознаваемой речи (или тишина)."
                )

            # 4. Обрезаем текст для защиты контекста LLM (максимум ~15к символов)
            clean_text = truncate_text(
                text.strip(),
                15000,
                suffix="\n... [Транскрибация обрезана: превышен лимит символов]",
            )

            # 5. Логируем в историю стейта
            rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()
            self.client.state.add_history(
                f"Транскрибирован '{rel_path}' ({format_size(size_bytes)})"
            )

            return SkillResult.ok(
                f"Результат транскрибации '{safe_path.name}':\n\n{clean_text}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except RuntimeError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            main_logger.error(f"[Cloud Whisper STT] Ошибка при транскрибации: {e}")
            return SkillResult.fail(f"Ошибка API при транскрибации: {e}")

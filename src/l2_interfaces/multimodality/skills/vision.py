"""
Навыки компьютерного зрения агента (Multimodal API).

Используются для конвертации локальных изображений/скриншотов в Base64
и инъекции их в промпт для моделей, поддерживающих Vision (например, gpt-4o, gemini-1.5).
"""

from src.l3_agent.skills.registry import SkillResult, skill
from src.l2_interfaces.multimodality.client import MultimodalityClient


class VisionSkills:
    """Навыки компьютерного зрения агента."""

    def __init__(self, client: MultimodalityClient) -> None:
        self.client = client

    @skill()
    async def look_at_image(self, filepath: str) -> SkillResult:
        """
        Размещает системный маркер изображения.
        ReactLoop перехватит этот маркер, считает файл с диска, конвертирует в Base64
        и передаст его в визуальный контекст LLM для анализа.

        Args:
            filepath: Относительный путь к картинке внутри директории `sandbox/`.
        """
        try:
            # Используем секьюрный гейткипер из Host OS
            safe_path = self.client.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл не найден ({filepath}).")

            ext = safe_path.suffix.lower()
            if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
                return SkillResult.fail(
                    f"Ошибка: Формат {ext} не поддерживается. Нужны изображения."
                )

            # Возвращаем системный маркер
            marker = f"[SYSTEM_MARKER_IMAGE_ATTACHED: {safe_path.resolve()}]"
            return SkillResult.ok(
                f"{marker}: True. Изображение успешно доставлено и уже находится в контексте. "
                f"[System]: Рекомендуется проанализировать медиа и сохранить краткое описание в метаданные (set_file_description). "
                f"Это привяжет текстовое описание к файлу."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при попытке посмотреть медиа: {e}")

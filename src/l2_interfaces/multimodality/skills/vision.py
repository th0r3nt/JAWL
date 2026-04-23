from src.l3_agent.skills.registry import SkillResult, skill
from src.l2_interfaces.multimodality.client import MultimodalityClient


class VisionSkills:
    """Навыки компьютерного зрения агента."""

    def __init__(self, client: MultimodalityClient):
        self.client = client

    @skill()
    async def look_at_media(self, filepath: str) -> SkillResult:
        """Смотрит на изображение (небходимо передать локальный путь к файлу) и помещает его в контекст для анализа на следующем шаге."""

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
                f"{marker}: True. Изображено успешно доставлено и уже находится в контексте. "
                f"[System]: Рекомендуется проанализировать медиа и сохранить краткое описание в метаданные с помощью сооветствующего навыка. "
                f"Это привяжет описание к файлу."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        
        except Exception as e:
            return SkillResult.fail(f"Ошибка при попытке посмотреть медиа: {e}")

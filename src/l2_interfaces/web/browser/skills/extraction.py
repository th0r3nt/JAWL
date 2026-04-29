import asyncio
from src.utils.logger import system_logger
from src.utils._tools import truncate_text, validate_sandbox_path, draw_image_grid
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.browser.client import WebBrowserClient


class BrowserExtraction:
    """
    Навыки для извлечения информации со страницы (скриншоты, сырой текст).
    """

    def __init__(self, client: WebBrowserClient):
        self.client = client

    @skill()
    async def take_screenshot(
        self,
        filename: str,
        with_grid: bool = True,
        grid_step: int = 100,
        full_page: bool = False,
    ) -> SkillResult:
        """
        Делает скриншот текущей страницы и автоматически инжектит картинку в мультимодальное зрение.

        with_grid: Накладывает контрастную координатную сетку поверх изображения.
        grid_step: Шаг сетки. Если нужна более точная сетка, можно передать 40.
        full_page: По умолчанию False (скринит только видимую часть экрана, чтобы картинка была максимально четкой).
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            if "/" not in filename and "\\" not in filename:
                filename = f"_system/download/{filename}"

            safe_path = validate_sandbox_path(filename)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # Делаем скриншот
            await self.client.page.screenshot(path=str(safe_path), full_page=full_page)

            # Накладываем крутую сетку
            if with_grid:
                await asyncio.to_thread(draw_image_grid, safe_path, grid_step)

            self.client.state.add_history(f"Скриншот: {safe_path.name} (Grid: {with_grid})")
            system_logger.info(f"[Web Browser] Сделан скриншот: {safe_path.name}")

            marker = f"[SYSTEM_MARKER_IMAGE_ATTACHED: {safe_path.resolve()}]"
            return SkillResult.ok(
                f"{marker}: True. Скриншот сделан и уже находится в вашем визуальном контексте. "
                f"Сохранен по пути: sandbox/{filename}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании скриншота: {e}")

    @skill()
    async def extract_text(self) -> SkillResult:
        """
        Извлекает весь сырой текст с текущей страницы (без HTML тегов).
        Полезно, если ARIA-дерево не дает нужной информации для чтения статьи.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            # JS-инъекция для получения чистого текста из body
            text = await self.client.page.evaluate("document.body.innerText")

            if not text or not text.strip():
                return SkillResult.fail("На странице не найдено текстового содержимого.")

            clean_text = truncate_text(text.strip(), 20000, "... [Текст обрезан]")

            self.client.state.add_history("Извлечение сырого текста")
            return SkillResult.ok(f"Текст страницы:\n\n{clean_text}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при извлечении текста: {e}")

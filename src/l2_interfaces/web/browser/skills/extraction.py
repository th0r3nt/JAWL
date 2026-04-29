import asyncio
from src.utils.logger import system_logger
from src.utils._tools import truncate_text, validate_sandbox_path
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.browser.client import WebBrowserClient


class BrowserExtraction:
    """
    Навыки для извлечения информации со страницы (скриншоты, сырой текст).
    """

    def __init__(self, client: WebBrowserClient):
        self.client = client

    @skill()
    async def take_screenshot(self, filename: str, with_grid: bool = True) -> SkillResult:
        """
        Делает скриншот текущей страницы и сохраняет в песочницу.
        Автоматически инжектит картинку в мультимодальное зрение на следующем шаге.
        with_grid: Если True, накладывает координатную сетку поверх изображения (помогает лучше вычислить координаты для click_coordinates).
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            if "/" not in filename and "\\" not in filename:
                filename = f"_system/download/{filename}"

            safe_path = validate_sandbox_path(filename)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            # Делаем скриншот всей страницы
            await self.client.page.screenshot(path=str(safe_path), full_page=True)

            # Накладываем сетку, если требуется
            if with_grid:
                def _draw_grid():
                    from PIL import Image, ImageDraw
                    
                    with Image.open(safe_path) as img:
                        # Создаем прозрачный слой для сетки
                        overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
                        draw = ImageDraw.Draw(overlay)
                        width, height = img.size
                        
                        grid_size = 100
                        
                        # Рисуем вертикальные и горизонтальные линии
                        for x in range(0, width, grid_size):
                            draw.line([(x, 0), (x, height)], fill=(255, 0, 0, 70), width=1)
                        for y in range(0, height, grid_size):
                            draw.line([(0, y), (width, y)], fill=(255, 0, 0, 70), width=1)

                        # Рисуем координаты пересечений
                        for x in range(0, width, grid_size):
                            for y in range(0, height, grid_size):
                                draw.text((x + 4, y + 4), f"{x},{y}", fill=(255, 0, 0, 200))

                        # Склеиваем слои и сохраняем
                        combined = Image.alpha_composite(img.convert('RGBA'), overlay)
                        combined.convert('RGB').save(safe_path)

                await asyncio.to_thread(_draw_grid)

            self.client.state.add_history(f"Скриншот: {safe_path.name} (Grid: {with_grid})")
            system_logger.info(f"[Web Browser] Сделан скриншот: {safe_path.name}")

            # Возвращаем системный маркер для мультимодальности
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

            # Защита от переполнения
            clean_text = truncate_text(text.strip(), 20000, "... [Текст обрезан]")

            self.client.state.add_history("Извлечение сырого текста")
            return SkillResult.ok(f"Текст страницы:\n\n{clean_text}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при извлечении текста: {e}")
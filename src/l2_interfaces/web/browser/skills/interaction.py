"""
Навыки физического воздействия на загруженную веб-страницу в браузере.
Позволяют кликать, печатать и наводить курсор (в том числе по абсолютным пиксельным координатам).
"""

from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.browser.client import WebBrowserClient


class BrowserInteraction:
    """
    Навыки для физического взаимодействия с элементами страницы (клики, ввод, клавиатура).
    """

    def __init__(self, client: WebBrowserClient):
        self.client = client

    @skill()
    async def click(self, role: str, name: str) -> SkillResult:
        """
        Выполняет симуляцию клика по элементу на основе его ARIA-роли.
        
        Args:
            role: ARIA-роль элемента (например, 'link', 'button').
            name: Внутреннее имя или текст элемента.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            locator = self.client.page.get_by_role(role, name=name, exact=True).first
            await locator.click()

            # Ждем возможных сетевых запросов после клика (например, загрузки SPA)
            try:
                await self.client.page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            await self.client.update_state_view()
            await self.client.save_session()

            self.client.state.add_history(f"Клик: [{role}] '{name}'")
            return SkillResult.ok("Клик выполнен. Состояние страницы обновлено в контексте.")

        except Exception as e:
            return SkillResult.fail(
                f"Не удалось кликнуть по элементу (Возможно он перекрыт или не найден): {e}"
            )

    @skill()
    async def hover(self, role: str, name: str) -> SkillResult:
        """
        Наводит курсор мыши на элемент. Полезно для раскрытия выпадающих меню (dropdown).
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            locator = self.client.page.get_by_role(role, name=name, exact=True).first
            await locator.hover()

            # Ждем анимацию появления меню
            await self.client.page.wait_for_timeout(1000)
            await self.client.update_state_view()

            self.client.state.add_history(f"Hover:[{role}] '{name}'")
            return SkillResult.ok("Курсор наведен на элемент. Дерево элементов обновлено.")

        except Exception as e:
            return SkillResult.fail(f"Не удалось навести курсор на элемент: {e}")

    @skill()
    async def fill_text(self, role: str, name: str, text: str) -> SkillResult:
        """
        Вводит текст в поле ввода.
        Например: role="textbox", name="Username", text="admin"
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            locator = self.client.page.get_by_role(role, name=name, exact=True).first
            await locator.fill(text)

            await self.client.update_state_view()
            self.client.state.add_history(f"Ввод текста в: [{role}] '{name}'")
            return SkillResult.ok("Текст успешно введен.")

        except Exception as e:
            return SkillResult.fail(f"Не удалось ввести текст: {e}")

    @skill()
    async def press_key(self, key: str) -> SkillResult:
        """
        Нажимает клавишу на клавиатуре.
        Полезно для отправки форм. 
        Примеры: 'Enter', 'Escape', 'Tab', 'ArrowDown'.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            await self.client.page.keyboard.press(key)

            try:
                await self.client.page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

            await self.client.update_state_view()
            self.client.state.add_history(f"Нажатие клавиши: {key}")
            return SkillResult.ok(f"Клавиша '{key}' нажата. Состояние обновлено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при нажатии клавиши: {e}")

    @skill()
    async def click_coordinates(self, x: int, y: int) -> SkillResult:
        """
        Кликает по точным абсолютным координатам 'x' и 'y' на странице.
        Эти координаты можно узнать, сделав скриншот с параметром координатной сетки.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            # Прокручиваем страницу так, чтобы элемент гарантированно попал во viewport (центрируем)
            scroll_x = max(0, x - 500)
            scroll_y = max(0, y - 300)
            await self.client.page.evaluate(
                f"window.scrollTo({{left: {scroll_x}, top: {scroll_y}, behavior: 'instant'}})"
            )
            await self.client.page.wait_for_timeout(500)

            # Вычисляем координаты относительно текущего viewport для клика мыши
            viewport_x = await self.client.page.evaluate(f"{x} - window.scrollX")
            viewport_y = await self.client.page.evaluate(f"{y} - window.scrollY")

            # Клик
            await self.client.page.mouse.click(viewport_x, viewport_y)
            
            try:
                await self.client.page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

            await self.client.update_state_view()
            await self.client.save_session()

            self.client.state.add_history(f"Клик по координатам: ({x}, {y})")
            return SkillResult.ok(f"Клик по абсолютным координатам ({x}, {y}) выполнен.")

        except Exception as e:
            return SkillResult.fail(f"Не удалось кликнуть по координатам: {e}")

    @skill()
    async def hover_coordinates(self, x: int, y: int) -> SkillResult:
        """
        Наводит курсор мыши на точные абсолютные координаты x и y на странице.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            scroll_x = max(0, x - 500)
            scroll_y = max(0, y - 300)
            await self.client.page.evaluate(
                f"window.scrollTo({{left: {scroll_x}, top: {scroll_y}, behavior: 'instant'}})"
            )
            await self.client.page.wait_for_timeout(500)

            viewport_x = await self.client.page.evaluate(f"{x} - window.scrollX")
            viewport_y = await self.client.page.evaluate(f"{y} - window.scrollY")

            await self.client.page.mouse.move(viewport_x, viewport_y)
            await self.client.page.wait_for_timeout(1000)
            
            await self.client.update_state_view()

            self.client.state.add_history(f"Hover по координатам: ({x}, {y})")
            return SkillResult.ok(f"Курсор наведен на координаты ({x}, {y}).")

        except Exception as e:
            return SkillResult.fail(f"Не удалось навести курсор: {e}")

    @skill()
    async def type_text(self, text: str) -> SkillResult:
        """
        Вводит текст с клавиатуры (имитируя нажатия клавиш) в текущий сфокусированный элемент.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            await self.client.page.keyboard.type(text)

            try:
                await self.client.page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

            await self.client.update_state_view()
            self.client.state.add_history("Ввод текста с клавиатуры")
            return SkillResult.ok(f"Текст '{text}' успешно напечатан.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при вводе текста: {e}")
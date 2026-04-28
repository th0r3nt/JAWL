from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.browser.client import WebBrowserClient


class BrowserNavigation:
    """
    Навыки для управления вкладками и перемещения в браузере.
    """

    def __init__(self, client: WebBrowserClient):
        self.client = client

    @skill()
    async def navigate(self, url: str) -> SkillResult:
        """
        Переходит по указанному URL (или обновляет страницу). 
        Запускает браузер, если он был закрыт.
        """

        try:
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            await self.client.ensure_browser()
            self.client.touch()

            await self.client.page.goto(url, wait_until="networkidle")
            await self.client.update_state_view()

            self.client.state.add_history(f"Переход на: {url}")
            system_logger.info(f"[Web Browser] Переход по ссылке: {url}")

            return SkillResult.ok(
                "Страница загружена. Изучите контекст интерфейса для просмотра элементов."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка загрузки страницы: {e}")

    @skill()
    async def scroll(self, direction: str = "down") -> SkillResult:
        """
        Прокручивает страницу вниз (down) или вверх (up) на один экран.
        """

        try:
            await self.client.ensure_browser()
            self.client.touch()

            sign = "" if direction == "down" else "-"
            # JS-инъекция для прокрутки на высоту окна (viewport)
            await self.client.page.evaluate(f"window.scrollBy(0, {sign}window.innerHeight)")

            # Даем время на подгрузку ленивых изображений/DOM (Lazy Load)
            await self.client.page.wait_for_timeout(1000)
            await self.client.update_state_view()

            self.client.state.add_history(f"Скролл: {direction}")
            return SkillResult.ok(
                f"Страница прокручена {direction}. Дерево элементов обновлено."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка скролла: {e}")

    @skill()
    async def close(self) -> SkillResult:
        """
        акрывает браузер. Рекомендуется вызывать после завершения работы с сайтом для экономии ОЗУ.
        """

        try:
            await self.client.close_browser()
            self.client.state.add_history("Браузер закрыт.")
            return SkillResult.ok("Браузер успешно закрыт. Память освобождена.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при закрытии браузера: {e}")

import time
import sys
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from src.utils.logger import system_logger
from src.utils._tools import truncate_text
from src.utils.settings import WebBrowserConfig
from src.l0_state.interfaces.state import WebBrowserState


class WebBrowserClient:
    """
    Stateful клиент для управления Playwright.
    Поддерживает ленивую загрузку (стартует только при первом запросе) и сохранение сессий (куки).
    """

    def __init__(self, state: WebBrowserState, config: WebBrowserConfig, data_dir: Path):
        self.state = state
        self.config = config

        self.profile_dir = data_dir / "interfaces" / "web" / "browser_profile"
        self.state_file = self.profile_dir / "storage_state.json"
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

        self.last_activity_time = time.time()
        self._lock = asyncio.Lock()

    async def start(self):
        self.state.is_online = True
        system_logger.info("[Web Browser] Интерфейс готов.")

    async def stop(self):
        await self.close_browser()
        self.state.is_online = False

    def touch(self):
        """
        Обновляет таймер активности для защиты от Watchdog'а.
        """

        self.last_activity_time = time.time()

    async def ensure_browser(self):
        """
        Гарантирует, что браузер запущен. Автоматически скачивает Chromium при первом запуске, если он не установлен.
        """

        async with self._lock:
            if self.page and not self.page.is_closed():
                return

            if not self.playwright:
                self.playwright = await async_playwright().start()

            if not self.browser:
                try:
                    self.browser = await self.playwright.chromium.launch(
                        headless=self.config.headless
                    )
                except Exception as e:
                    # Если Playwright жалуется на отсутствие браузеров - качаем их сами
                    if "playwright install" in str(e):
                        system_logger.info(
                            "[Web Browser] Бинарники Chromium не найдены. Начата автоматическая загрузка. (пару минут)."
                        )

                        proc = await asyncio.create_subprocess_exec(
                            sys.executable,
                            "-m",
                            "playwright",
                            "install",
                            "chromium",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        await proc.communicate()

                        system_logger.info(
                            "[Web Browser] Загрузка Chromium завершена. Запуск браузера."
                        )

                        # Повторная попытка запуска после установки
                        self.browser = await self.playwright.chromium.launch(
                            headless=self.config.headless
                        )
                    else:
                        raise

            # Настройка контекста
            context_kwargs = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }

            # Подхватываем сохраненную сессию (куки, авторизации), если она есть
            if self.state_file.exists():
                context_kwargs["storage_state"] = str(self.state_file)

            self.context = await self.browser.new_context(**context_kwargs)
            self.page = await self.context.new_page()

            # Устанавливаем дефолтный таймаут для всех действий (в мс)
            self.page.set_default_timeout(self.config.timeout_sec * 1000)

            system_logger.info("[Web Browser] Запущен процесс Chromium.")

    async def save_session(self):
        """
        Сохраняет куки и Local Storage на диск.
        """

        if self.context:
            await self.context.storage_state(path=str(self.state_file))

    async def close_browser(self):
        """
        Штатно закрывает браузер и освобождает ОЗУ.
        """

        async with self._lock:
            if self.context:
                await self.save_session()

            if self.browser:
                await self.browser.close()
                system_logger.info("[Web Browser] Процесс Chromium остановлен.")

            self.browser = None
            self.context = None
            self.page = None
            self.state.is_open = False
            self.state.viewport = "Браузер закрыт."

    async def update_state_view(self):
        """
        Обновляет L0 State: URL, Title и парсит дерево элементов страницы (AOM).
        """

        if not self.page or self.page.is_closed():
            self.state.is_open = False
            self.state.viewport = "Браузер закрыт."
            return

        self.state.is_open = True
        self.state.current_url = self.page.url
        self.state.page_title = await self.page.title()

        try:
            # В новых версиях Playwright (>=1.49) page.accessibility удален
            # Вместо него используется aria_snapshot, который идеально подходит для ИИ-агентов
            # и возвращает готовую легковесную YAML-структуру
            snapshot = await self.page.locator("body").aria_snapshot()

            if snapshot:
                # Защита от переполнения контекста (для гигантских страниц)
                self.state.viewport = truncate_text(
                    snapshot,
                    15000,
                    "...[Страница слишком длинная: обрезана. Для дальнейшего просмотра - скролл]",
                )
            else:
                self.state.viewport = (
                    "Дерево элементов пусто (возможно, страница не успела загрузиться)."
                )
        except Exception as e:
            self.state.viewport = f"Ошибка построения дерева элементов: {e}"

    def _flatten_aom(self, node: dict, depth: int = 0) -> list[str]:
        """
        Рекурсивно превращает JSON AOM в плоский Markdown-подобный список.
        """

        lines = []
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")

        # Игнорируем бесполезный визуальный мусор, оставляем контент и интерактив
        ignore_roles = {"generic", "WebArea", "presentation", "none"}

        if role and role not in ignore_roles:
            indent = "  " * min(depth, 5)  # Ограничиваем отступы
            text = f"{indent}- [{role}]"
            if name:
                text += f" '{name}'"
            if value:
                text += f" (Значение: {value})"

            # Помечаем интерактивные элементы, чтобы LLM понимала, куда можно кликать
            if role in ("link", "button", "textbox", "searchbox", "checkbox", "combobox"):
                text += " *интерактивный*"

            lines.append(text)

        for child in node.get("children", []):
            lines.extend(self._flatten_aom(child, depth + 1))

        return lines

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для агента.
        """

        if not self.state.is_online:
            return "### WEB BROWSER [OFF]\nИнтерфейс отключен."

        if not self.state.is_open:
            return (
                "### WEB BROWSER [ON]\nБраузер закрыт. Для запуска - вызвать навык навигации."
            )

        history_str = (
            "\n".join(f"  - {h}" for h in self.state.history)
            if self.state.history
            else "  Пусто"
        )

        return f"""### WEB BROWSER [ON]
* Текущая вкладка: {self.state.page_title}
* URL: {self.state.current_url}
* Последние действия:
{history_str}

* Видимые элементы (AOM):
{self.state.viewport}
"""

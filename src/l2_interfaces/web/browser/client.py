"""
Stateful-менеджер Headless-браузера (Playwright).

Обеспечивает "ленивую" (Lazy) инициализацию процесса Chromium, чтобы не тратить ОЗУ,
если агент ничего не ищет. Управляет состоянием хранилища (Cookie, Local Storage)
для обхода повторной авторизации на сайтах. Конвертирует DOM в легкий Markdown (AOM).
"""

import time
import sys
import asyncio
from pathlib import Path
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from src.utils.logger import system_logger
from src.utils._tools import truncate_text
from src.utils.settings import WebBrowserConfig
from src.l0_state.interfaces.state import WebBrowserState


class WebBrowserClient:
    """
    Stateful клиент для управления Playwright.
    Поддерживает ленивую загрузку и сохранение сессий (куки).
    """

    def __init__(
        self, state: WebBrowserState, config: WebBrowserConfig, data_dir: Path
    ) -> None:
        """
        Инициализирует менеджер браузера.

        Args:
            state: L0 стейт (приборная панель).
            config: Конфигурация браузера (headless, timeouts).
            data_dir: Корневая директория локальных данных.
        """

        self.state = state
        self.config = config

        self.profile_dir = data_dir / "interfaces" / "web" / "browser_profile"
        self.state_file = self.profile_dir / "storage_state.json"
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self.last_activity_time: float = time.time()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Вызывается при старте системы (браузер физически не запускается до первого обращения)."""
        self.state.is_online = True
        system_logger.info("[Web Browser] Интерфейс готов.")

    async def stop(self) -> None:
        """Штатно закрывает браузер при остановке системы."""
        await self.close_browser()
        self.state.is_online = False

    def touch(self) -> None:
        """
        Обновляет таймер активности для защиты от Watchdog'а.
        """
        self.last_activity_time = time.time()

    async def ensure_browser(self) -> None:
        """
        Гарантирует, что браузер запущен. Автоматически скачивает Chromium при
        первом запуске, если бинарники отсутствуют на хосте.
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
                            "[Web Browser] Бинарники Chromium не найдены. Начата автоматическая загрузка (займет пару минут)."
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

    async def save_session(self) -> None:
        """Сохраняет куки и Local Storage на диск (в state_file)."""
        if self.context:
            await self.context.storage_state(path=str(self.state_file))

    async def close_browser(self) -> None:
        """Штатно закрывает браузер и освобождает ОЗУ."""
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

    async def update_state_view(self) -> None:
        """
        Конвертирует DOM-дерево текущей веб-страницы в плоскую AOM (Accessibility Object Model)
        YAML-структуру (через aria_snapshot). Вырезает визуальный мусор,
        оставляя агенту только текст и кликабельные (интерактивные) элементы.
        """
        if not self.page or self.page.is_closed():
            self.state.is_open = False
            self.state.viewport = "Браузер закрыт."
            return

        self.state.is_open = True
        self.state.current_url = self.page.url
        self.state.page_title = await self.page.title()

        try:
            # aria_snapshot идеально подходит для ИИ-агентов (возвращает легкий YAML)
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

    async def get_context_block(self, **kwargs: Any) -> str:
        """Провайдер контекста для агента."""
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

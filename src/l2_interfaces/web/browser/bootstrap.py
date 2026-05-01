"""
Инициализатор интерфейса Web Browser (Playwright).

Оркестрирует запуск headless-браузера, регистрацию навыков навигации/парсинга
и поднятие фонового Watchdog-а для защиты ОЗУ от утечек (авто-закрытие простаивающих сессий).
"""

from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger

from src.l2_interfaces.web.browser.client import WebBrowserClient
from src.l2_interfaces.web.browser.events import WebBrowserEvents

from src.l2_interfaces.web.browser.skills.navigation import BrowserNavigation
from src.l2_interfaces.web.browser.skills.interaction import BrowserInteraction
from src.l2_interfaces.web.browser.skills.extraction import BrowserExtraction

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_web_browser(system: "System") -> List[Any]:
    """
    Инициализирует интерфейс полноценного браузера.

    Args:
        system (System): Главный DI-контейнер фреймворка.

    Returns:
        List[Any]: Компоненты жизненного цикла (client, events).
    """
    config = system.interfaces_config.web.browser

    if not hasattr(system, "web_browser_state"):
        from src.l0_state.interfaces.state import WebBrowserState

        system.web_browser_state = WebBrowserState()

    client = WebBrowserClient(
        state=system.web_browser_state, config=config, data_dir=system.local_data_dir
    )

    events = WebBrowserEvents(client=client)

    # Регистрируем навыки (навигация, клики, скролл, скриншоты)
    register_instance(BrowserNavigation(client))
    register_instance(BrowserInteraction(client))
    register_instance(BrowserExtraction(client))

    system.context_registry.register_provider(
        name="web browser",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )
    system_logger.info("[Web Browser] Интерфейс загружен. Готов к запуску Playwright.")

    return [client, events]

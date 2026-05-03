"""
Главный инициализатор слоя интерфейсов (L2).

Оркестрирует запуск всех системных модулей (Host, Web, Telegram, Github и др.)
на основе конфигурации `interfaces.yaml`. Если интерфейс аппаратно отключен,
модуль регистрирует заглушку (OFF Provider), чтобы агент видел это в своем промпте.
"""

from typing import List, Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.main import System

# Импорт интерфейсов
from src.l2_interfaces.host.os.bootstrap import setup_host_os
from src.l2_interfaces.host.terminal.bootstrap import setup_host_terminal
from src.l2_interfaces.code_graph.bootstrap import setup_code_graph
from src.l2_interfaces.meta.bootstrap import setup_meta
from src.l2_interfaces.telegram.telethon.bootstrap import setup_telethon
from src.l2_interfaces.telegram.aiogram.bootstrap import setup_aiogram
from src.l2_interfaces.web.search.bootstrap import setup_web_search
from src.l2_interfaces.web.http.bootstrap import setup_web_http
from src.l2_interfaces.web.browser.bootstrap import setup_web_browser
from src.l2_interfaces.web.hooks.bootstrap import setup_web_hooks
from src.l2_interfaces.web.rss.bootstrap import setup_web_rss
from src.l2_interfaces.multimodality.bootstrap import setup_multimodality
from src.l2_interfaces.calendar.bootstrap import setup_calendar
from src.l2_interfaces.github.bootstrap import setup_github

# Импортируйте сюда свой кастомный интерфейс
# from src.l2_interfaces.interface_name.bootstrap import setup_interface

from src.l3_agent.context.registry import ContextSection


def off_provider(name: str) -> Any:
    """
    Создает заглушку-провайдер контекста для аппаратно отключенных интерфейсов.
    Агент будет видеть этот статус и понимать, что инструмент недоступен.

    Args:
        name: Человекочитаемое имя интерфейса (например 'HOST OS').

    Returns:
        Асинхронная функция-провайдер контекста.
    """

    async def provider(**kwargs: Any) -> str:
        return f"### {name} [OFF]\nИнтерфейс отключен."

    return provider


def initialize_l2_interfaces(
    system: "System", env_vars: Dict[str, Optional[str]]
) -> List[Any]:
    """
    Оркестрирует запуск L2 интерфейсов. Читает yaml-конфиг и дергает нужные бутстрапы.
    Возвращает список компонентов (lifecycle_components), у которых есть жизненный цикл (start/stop).

    Args:
        system: Главный DI-контейнер системы.
        env_vars: Словарь с секретными токенами из .env файла.

    Returns:
        Список инициализированных компонентов для Event Loop.
    """

    config = system.interfaces_config
    components: List[Any] = []

    # ================================================================
    # HOST OS
    # ================================================================

    if config.host.os.enabled:
        components.extend(setup_host_os(system))
    else:
        system.context_registry.register_provider(
            "host os", off_provider("HOST OS"), ContextSection.INTERFACES
        )

    # ================================================================
    # HOST TERMINAL
    # ================================================================

    if config.host.terminal.enabled:
        components.extend(setup_host_terminal(system))
    else:
        system.context_registry.register_provider(
            "host terminal", off_provider("HOST TERMINAL"), ContextSection.INTERFACES
        )

    # ================================================================
    # CODE GRAPH
    # ================================================================

    if getattr(config, "code_graph", None) and getattr(config.code_graph, "enabled", False):
        components.extend(setup_code_graph(system))
    else:
        system.context_registry.register_provider(
            "code_graph", off_provider("CODE GRAPH"), ContextSection.INTERFACES
        )

    # ================================================================
    # TELEGRAM TELETHON
    # ================================================================

    if config.telegram.telethon.enabled:
        components.extend(
            setup_telethon(
                system=system,
                api_id=env_vars.get("TELETHON_API_ID"),
                api_hash=env_vars.get("TELETHON_API_HASH"),
            )
        )
    else:
        system.context_registry.register_provider(
            "telethon", off_provider("TELETHON"), ContextSection.INTERFACES
        )

    # ================================================================
    # TELEGRAM AIOGRAM
    # ================================================================

    if config.telegram.aiogram.enabled:
        components.extend(
            setup_aiogram(
                system=system,
                bot_token=env_vars.get("AIOGRAM_BOT_TOKEN"),
            )
        )
    else:
        system.context_registry.register_provider(
            "aiogram", off_provider("AIOGRAM"), ContextSection.INTERFACES
        )

    # ================================================================
    # GITHUB
    # ================================================================

    if config.github.enabled:
        components.extend(
            setup_github(
                system=system,
                token=env_vars.get("GITHUB_TOKEN"),
            )
        )
    else:
        system.context_registry.register_provider(
            "github", off_provider("GITHUB"), ContextSection.INTERFACES
        )

    # ================================================================
    # EMAIL
    # ================================================================

    if config.email.enabled:
        from src.l2_interfaces.email.bootstrap import setup_email

        components.extend(
            setup_email(
                system=system,
                account=env_vars.get("EMAIL_ACCOUNT"),
                password=env_vars.get("EMAIL_PASSWORD"),
            )
        )
    else:
        system.context_registry.register_provider(
            "email", off_provider("EMAIL"), ContextSection.INTERFACES
        )

    # ================================================================
    # WEB SEARCH
    # ================================================================

    if config.web.search.enabled:
        components.extend(setup_web_search(system, env_vars.get("TAVILY_API_KEY")))
    else:
        system.context_registry.register_provider(
            "web search", off_provider("WEB SEARCH"), ContextSection.INTERFACES
        )

    # ================================================================
    # WEB HTTP
    # ================================================================

    if config.web.http.enabled:
        components.extend(setup_web_http(system))
    else:
        system.context_registry.register_provider(
            "web http", off_provider("WEB HTTP"), ContextSection.INTERFACES
        )

    # ================================================================
    # WEB BROWSER
    # ================================================================

    if config.web.browser.enabled:
        components.extend(setup_web_browser(system))
    else:
        system.context_registry.register_provider(
            "web browser", off_provider("WEB BROWSER"), ContextSection.INTERFACES
        )

    # ================================================================
    # WEB HOOKS
    # ================================================================

    if config.web.hooks.enabled:
        components.extend(
            setup_web_hooks(system=system, secret_token=env_vars.get("WEBHOOK_SECRET"))
        )
    else:
        system.context_registry.register_provider(
            "web hooks", off_provider("WEB HOOKS"), ContextSection.INTERFACES
        )

    # ================================================================
    # WEB RSS
    # ================================================================

    if config.web.rss.enabled:
        components.extend(setup_web_rss(system))
    else:
        system.context_registry.register_provider(
            "web rss", off_provider("WEB RSS"), ContextSection.INTERFACES
        )

    # ================================================================
    # META
    # ================================================================

    if config.meta.enabled:
        components.extend(setup_meta(system))
    else:
        # Кастомный провайдер для Meta, чтобы показывать статус скиллов даже в OFF режиме
        async def meta_off_provider(**kwargs: Any) -> str:
            custom_status = (
                "включены (но интерфейс отключен)"
                if config.meta.custom_skills_enabled
                else "отключены"
            )
            return f"### META [OFF]\nИнтерфейс отключен.\n* Custom Skills: {custom_status}"

        system.context_registry.register_provider(
            "meta", meta_off_provider, ContextSection.INTERFACES
        )

    # ================================================================
    # MULTIMODALITY
    # ================================================================

    if config.multimodality.enabled:
        components.extend(setup_multimodality(system))
    else:
        system.context_registry.register_provider(
            "multimodality", off_provider("MULTIMODALITY"), ContextSection.INTERFACES
        )

    # ================================================================
    # CALENDAR
    # ================================================================

    if config.calendar.enabled:
        components.extend(setup_calendar(system))
    else:
        system.context_registry.register_provider(
            "calendar", off_provider("CALENDAR"), ContextSection.INTERFACES
        )

    # ================================================================

    return components  # Возвращает список компонентов, которые нужно запустить в main.py (например, поллинг Telethon или календаря, если они включены)

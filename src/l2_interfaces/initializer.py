from typing import List, Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from src.main import System

# Импорт интерфейсов
from src.l2_interfaces.host.os.bootstrap import setup_host_os
from src.l2_interfaces.meta.bootstrap import setup_meta
from src.l2_interfaces.telegram.telethon.bootstrap import setup_telethon
from src.l2_interfaces.telegram.aiogram.bootstrap import setup_aiogram
from src.l2_interfaces.web.search.bootstrap import setup_web_search
from src.l2_interfaces.multimodality.bootstrap import setup_multimodality
from src.l2_interfaces.calendar.bootstrap import setup_calendar
from src.l2_interfaces.github.bootstrap import setup_github

# Импортируйте сюда свой кастомный интерфейс
# from src.l2_interfaces.interface_name.bootstrap import setup_interface

from src.l3_agent.context.registry import ContextSection


def make_off_provider(name: str):
    """Создает заглушку-провайдер контекста для аппаратно отключенных интерфейсов."""

    async def provider(**kwargs) -> str:
        return f"### {name} [OFF]\nИнтерфейс отключен."

    return provider


def initialize_l2_interfaces(system: "System", env_vars: Dict[str, str | None]) -> List[Any]:
    """
    Оркестрирует запуск L2 интерфейсов. Читает yaml-конфиг и дергает нужные бутстрапы.
    Возвращает список компонентов (lifecycle_components), у которых есть start() и stop().
    """

    config = system.interfaces_config
    components = []

    # ================================================================
    # HOST OS
    # ================================================================

    if config.host.os.enabled:
        components.extend(setup_host_os(system))
    else:
        system.context_registry.register_provider(
            "host os", make_off_provider("HOST OS"), ContextSection.INTERFACES
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
            "telethon", make_off_provider("TELETHON"), ContextSection.INTERFACES
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
            "aiogram", make_off_provider("AIOGRAM"), ContextSection.INTERFACES
        )

    # ================================================================
    # GITHUB
    # ================================================================

    if getattr(config, "github", None) and config.github.enabled:
        components.extend(
            setup_github(
                system=system,
                token=env_vars.get("GITHUB_TOKEN"),
            )
        )
    else:
        system.context_registry.register_provider(
            "github", make_off_provider("GITHUB"), ContextSection.INTERFACES
        )

    # ================================================================
    # EMAIL
    # ================================================================

    if getattr(config, "email", None) and config.email.enabled:
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
            "email", make_off_provider("EMAIL"), ContextSection.INTERFACES
        )

    # ================================================================
    # WEB SEARCH
    # ================================================================

    if config.web.search.enabled:
        components.extend(setup_web_search(system))
    else:
        system.context_registry.register_provider(
            "web search", make_off_provider("WEB SEARCH"), ContextSection.INTERFACES
        )

    # ================================================================
    # META
    # ================================================================

    if getattr(config, "meta", None) and config.meta.enabled:
        components.extend(setup_meta(system))
    else:
        system.context_registry.register_provider(
            "meta", make_off_provider("META"), ContextSection.INTERFACES
        )

    # ================================================================
    # MULTIMODALITY
    # ================================================================

    if getattr(config, "multimodality", None) and config.multimodality.enabled:
        components.extend(setup_multimodality(system))
    else:
        system.context_registry.register_provider(
            "multimodality", make_off_provider("MULTIMODALITY"), ContextSection.INTERFACES
        )

    # ================================================================
    # CALENDAR
    # ================================================================

    if getattr(config, "calendar", None) and config.calendar.enabled:
        components.extend(setup_calendar(system))
    else:
        system.context_registry.register_provider(
            "calendar", make_off_provider("CALENDAR"), ContextSection.INTERFACES
        )

    # ================================================================

    return components  # Возвращает список компонентов, которые нужно запустить в main.py (например, поллинг Telethon или календаря, если они включены)

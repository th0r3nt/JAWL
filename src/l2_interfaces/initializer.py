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
from src.l2_interfaces.reddit.bootstrap import setup_reddit

# Импортируйте сюда свой кастомный интерфейс
# from src.l2_interfaces.interface_name.bootstrap import setup_interface


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

    # ================================================================
    # WEB SEARCH
    # ================================================================

    if config.web.search.enabled:
        components.extend(setup_web_search(system))

    # ================================================================
    # META
    # ================================================================

    if getattr(config, "meta", None) and config.meta.enabled:
        components.extend(setup_meta(system))

    # ================================================================
    # MULTIMODALITY
    # ================================================================

    if getattr(config, "multimodality", None) and config.multimodality.enabled:
        components.extend(setup_multimodality(system))

    # ================================================================
    # CALENDAR
    # ================================================================

    if getattr(config, "calendar", None) and config.calendar.enabled:
        components.extend(setup_calendar(system))

    # ================================================================
    # REDDIT
    # ================================================================
    if getattr(config, "reddit", None) and config.reddit.enabled:
        components.extend(
            setup_reddit(
                system=system,
                client_id=env_vars.get("REDDIT_CLIENT_ID"),
                client_secret=env_vars.get("REDDIT_CLIENT_SECRET"),
            )
        )

    # ================================================================

    return components  # Возвращает список компонентов, которые нужно запустить в main.py (например, поллинг Telethon или календаря, если они включены)

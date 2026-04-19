from typing import List, Any, Dict, TYPE_CHECKING

from src.l2_interfaces.host.os.bootstrap import setup_host_os
from src.l2_interfaces.meta.bootstrap import setup_meta
from src.l2_interfaces.telegram.telethon.bootstrap import setup_telethon
from src.l2_interfaces.telegram.aiogram.bootstrap import setup_aiogram
from src.l2_interfaces.web.search.bootstrap import setup_web_search

# TODO: from src.l2_interfaces.web.http.bootstrap import setup_web_http

if TYPE_CHECKING:
    from src.main import System


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
    # META
    # ================================================================

    if getattr(config, "meta", None) and config.meta.enabled:
        components.extend(setup_meta(system))

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

    return components  # Возвращает список компонентов, которые нужно запустить в main.py (например, поллинг Telethon, если он включен)

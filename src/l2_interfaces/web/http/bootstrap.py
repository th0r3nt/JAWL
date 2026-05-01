"""
Инициализатор интерфейса Web HTTP.

Внедряет в агента навыки сырых HTTP-запросов (GET/POST)
и прямых загрузок файлов с сохранением в песочницу, минуя тяжелый браузер.
"""

from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger

from src.l2_interfaces.web.http.client import WebHTTPClient
from src.l2_interfaces.web.http.skills.requests import WebHTTPRequests

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_web_http(system: "System") -> List[Any]:
    """
    Инициализирует легковесный интерфейс Web HTTP.

    Args:
        system (System): Главный DI-контейнер фреймворка.

    Returns:
        List[Any]: Пустой список (нет фоновых задач).
    """
    
    config = system.interfaces_config.web.http

    client = WebHTTPClient(state=system.web_http_state, config=config)

    register_instance(WebHTTPRequests(client))

    system.context_registry.register_provider(
        name="web http",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )
    system_logger.info("[Web HTTP] Интерфейс загружен.")

    return []

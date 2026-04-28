from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger

from src.l2_interfaces.web.http.client import WebHTTPClient
from src.l2_interfaces.web.http.skills.requests import WebHTTPRequests

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_web_http(system: "System") -> List[Any]:
    """Инициализирует интерфейс Web HTTP."""
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

from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import register_instance

from src.l2_interfaces.web.search.client import WebSearchClient
from src.l2_interfaces.web.search.skills.duckduckgo import DuckDuckGoSearch
from src.l2_interfaces.web.search.skills.webpages import WebPages

if TYPE_CHECKING:
    from src.main import System


def setup_web_search(system: "System") -> List[Any]:
    """Инициализирует Web-интерфейс."""

    web_search_config = system.interfaces_config.web.search
    client = WebSearchClient(
        state=system.web_search_state,
        request_timeout=web_search_config.request_timeout_sec,
        max_page_chars=web_search_config.max_page_chars,
    )

    web_search = DuckDuckGoSearch(client=client)
    web_pages = WebPages(client=client)

    # Регистрация навыков для агента
    register_instance(web_search)
    register_instance(web_pages)

    # Регистрация провайдеров контекста (отдают Markdown блоки в промпт агента)
    system.context_registry.register_provider(name="web search", provider_func=client.get_context_block, priority=100)
    system_logger.info("[System] Интерфейс Web загружен.")

    return []

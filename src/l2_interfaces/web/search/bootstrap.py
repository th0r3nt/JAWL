from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger

from src.l2_interfaces.web.search.client import WebSearchClient
from src.l2_interfaces.web.search.skills.duckduckgo_search import DuckDuckGoSearch
from src.l2_interfaces.web.search.skills.tavily_search import TavilySearch
from src.l2_interfaces.web.search.skills.trafilatura_read import TrafilaturaReader
from src.l2_interfaces.web.search.skills.jina_read import JinaReader
from src.l2_interfaces.web.search.skills.research import DeepResearch

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_web_search(system: "System", tavily_api_key: str | None) -> List[Any]:
    """Инициализирует Web-интерфейс."""
    config = system.interfaces_config.web.search
    client = WebSearchClient(
        state=system.web_search_state,
        request_timeout=config.request_timeout_sec,
        max_page_chars=config.max_page_chars,
        deep_research_config=config.deep_research,
    )

    # =================================================================
    # Сборка поисковика

    active_searcher = None

    # Вначале пробуем инициализировать крутой Tavily
    if config.search_engine == "tavily":
        if tavily_api_key:
            active_searcher = TavilySearch(client=client, api_key=tavily_api_key)
            system_logger.info("[Web] Инициализация клиента поиска веб-страниц: Tavily")
        else:
            system_logger.warning(
                "[Web] TAVILY_API_KEY не найден в .env. Применяется Fallback на DuckDuckGo."
            )

    # Если Tavily не прошел проверки или юзер выбрал duckduckgo (kb,j вписал дичь в конфиг)
    if active_searcher is None:
        active_searcher = DuckDuckGoSearch(client=client)
        system_logger.info("[Web] Инициализация клиента поиска веб-страниц: DuckDuckGo")

    # =================================================================
    # Сборка читалки страниц

    if config.reader_engine == "jina":
        active_reader = JinaReader(client=client)
        system_logger.info("[Web] Инициализация клиента чтения веб-страниц: Jina Reader")
    else:
        if config.reader_engine != "trafilatura":
            system_logger.warning(
                f"[Web] Неизвестный клиент чтения веб-страниц '{config.reader_engine}'. Fallback на Trafilatura."
            )

        active_reader = TrafilaturaReader(client=client)
        system_logger.info("[Web] Инициализация клиента чтения веб-страниц: Trafilatura")

    # =================================================================
    # Инъекция в DeepResearch

    deep_research = DeepResearch(client=client, searcher=active_searcher, reader=active_reader)

    # Регистрация навыков
    register_instance(active_searcher)
    register_instance(active_reader)
    register_instance(deep_research)

    system.context_registry.register_provider(
        name="web search",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )
    system_logger.info("[Web] Интерфейс загружен.")

    return []

"""
Плагин интерфейса Web Search & Deep Research.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.web.search.state import WebSearchState
from src.l2_interfaces.web.search.client import WebSearchClient

from src.l2_interfaces.web.search.skills.duckduckgo_search import DuckDuckGoSearch
from src.l2_interfaces.web.search.skills.tavily_search import TavilySearch
from src.l2_interfaces.web.search.skills.trafilatura_read import TrafilaturaReader
from src.l2_interfaces.web.search.skills.jina_read import JinaReader
from src.l2_interfaces.web.search.skills.research import DeepResearch

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class WebSearchPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "WEB SEARCH"

    @property
    def description(self) -> str:
        return "Search engines and web page parsers."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.web.search.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        config = container.interfaces_config.web.search

        state = WebSearchState(history_limit=10)
        container.l0_states["web_search"] = state

        client = WebSearchClient(
            state=state,
            request_timeout=config.request_timeout_sec,
            max_page_chars=config.max_page_chars,
            deep_research_config=config.deep_research,
        )

        tavily_api_key = env_vars.get("TAVILY_API_KEY")
        active_searcher = None

        if config.search_engine == "tavily":
            if tavily_api_key:
                active_searcher = TavilySearch(client=client, api_key=tavily_api_key)
                main_logger.info("[Web Search] Поиск через: Tavily")
            else:
                main_logger.warning(
                    "[Web Search] TAVILY_API_KEY не найден. Fallback на DuckDuckGo."
                )

        if active_searcher is None:
            active_searcher = DuckDuckGoSearch(client=client)
            main_logger.info("[Web Search] Поиск через: DuckDuckGo")

        if config.reader_engine == "jina":
            active_reader = JinaReader(client=client)
            main_logger.info("[Web Search] Читалка страниц: Jina Reader")
        else:
            if config.reader_engine != "trafilatura":
                main_logger.warning(
                    f"[Web Search] Неизвестная читалка '{config.reader_engine}'. Fallback на Trafilatura."
                )
            active_reader = TrafilaturaReader(client=client)
            main_logger.info("[Web Search] Читалка страниц: Trafilatura")

        deep_research = DeepResearch(
            client=client, searcher=active_searcher, reader=active_reader
        )

        register_instance(active_searcher)
        register_instance(active_reader)
        register_instance(deep_research)

        container.context_registry.register_provider(
            name=self.name.lower().replace(" ", "_"),
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Web Search] Интерфейс загружен..")
        return []

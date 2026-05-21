"""
L2 client for Web Search interface.

Configures search timeout, page limits, and handles search history context.
"""

from typing import Any

from src.l2_interfaces.web.search.state import WebSearchState
from src.utils.settings import DeepResearchConfig


class WebSearchClient:
    """Base client for the web search interface."""

    def __init__(
        self,
        state: WebSearchState,
        request_timeout: int = 15,
        max_page_chars: int = 15000,
        deep_research_config: DeepResearchConfig = None,
    ) -> None:
        """
        Initializes web client settings.

        Args:
            state: L0 state (agent dashboard).
            request_timeout: Timeout for loading pages.
            max_page_chars: Strict character limit when reading a single page.
            deep_research_config: Configuration for the parallel fact-gathering skill.
        """

        self.state = state
        self.timeout = request_timeout
        self.max_page_chars = max_page_chars
        self.deep_research_config = deep_research_config
        self.state.is_online = True  # If initialized, consider enabled

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Context provider for ContextRegistry.
        Returns formatted context block for the agent (browsing history).
        """

        desc = "Description: Search engines (DuckDuckGo/Tavily) and web page parsers."
        if not self.state.is_online:
            return f"### WEB SEARCH [OFF] \n{desc}\nThe interface is disabled."

        return f"### WEB SEARCH [ON] \n{desc}\n{self.state.browser_history}"

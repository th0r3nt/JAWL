"""
Клиент Web Search интерфейса.

Хранит общие константы, таймауты и лимиты для веб-поиска и парсинга страниц.
Служит провайдером истории веб-серфинга агента.
"""

from typing import Any

from src.l0_state.interfaces.state import WebSearchState
from src.utils.settings import DeepResearchConfig


class WebSearchClient:
    """Базовый клиент веб-интерфейса."""

    def __init__(
        self,
        state: WebSearchState,
        request_timeout: int = 15,
        max_page_chars: int = 15000,
        deep_research_config: DeepResearchConfig = None,
    ) -> None:
        """
        Инициализирует настройки веб-клиента.

        Args:
            state: L0 стейт (приборная панель агента).
            request_timeout: Таймаут на загрузку страниц.
            max_page_chars: Жесткий лимит символов при чтении одной страницы.
            deep_research_config: Конфигурация для навыка параллельного сбора информации.
        """
        self.state = state
        self.timeout = request_timeout
        self.max_page_chars = max_page_chars
        self.deep_research_config = deep_research_config
        self.state.is_online = True  # Если инициализирован, считаем включенным

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок контекста для агента (история серфинга).
        """
        if not self.state.is_online:
            return "### WEB SEARCH [OFF] \nИнтерфейс отключен."

        return f"### WEB SEARCH [ON] \n{self.state.browser_history}"

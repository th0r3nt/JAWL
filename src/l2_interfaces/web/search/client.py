from src.l0_state.interfaces.state import WebSearchState


class WebClient:
    """
    Базовый клиент веб-интерфейса.
    Хранит общие константы и настройки для веб-скиллов.
    """

    def __init__(
        self, state: WebSearchState, request_timeout: int = 15, max_page_chars: int = 15000
    ):
        self.state = state
        self.timeout = request_timeout
        self.max_page_chars = max_page_chars
        self.state.is_online = True  # Если инициализирован, считаем включенным

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок контекста для агента.
        """

        status = "ON" if self.state.is_online else "OFF"
        data = self.state.browser_history if self.state.is_online else "Интерфейс отключен."
        return f"### WEB [{status}]\n{data}"
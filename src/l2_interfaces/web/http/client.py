from src.l0_state.interfaces.web.http_state import WebHTTPState
from src.utils.settings import WebHTTPConfig


class WebHTTPClient:
    def __init__(self, state: WebHTTPState, config: WebHTTPConfig):
        self.state = state
        self.config = config
        self.state.is_online = True

    async def get_context_block(self, **kwargs) -> str:
        if not self.state.is_online:
            return "### WEB HTTP [OFF]\nИнтерфейс отключен."

        return f"### WEB HTTP [ON]\n* История запросов:\n{self.state.http_history}"

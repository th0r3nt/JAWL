from src.l2_interfaces.web.http.state import WebHTTPState
from src.utils.settings import WebHTTPConfig


class WebHTTPClient:
    def __init__(self, state: WebHTTPState, config: WebHTTPConfig):
        self.state = state
        self.config = config
        self.state.is_online = True

    async def get_context_block(self, **kwargs) -> str:
        desc = "Description: Raw HTTP requests and file downloading."
        if not self.state.is_online:
            return f"### WEB HTTP [OFF]\n{desc}\nThe interface is disabled."

        return f"### WEB HTTP [ON]\n{desc}\n* Query history:\n{self.state.http_history}"

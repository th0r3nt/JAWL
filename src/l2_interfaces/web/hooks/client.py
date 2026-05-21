"""
L2 client for Web Hooks interface.

Manages configuration and handles system prompt preview.
"""

from typing import Any
from src.l2_interfaces.web.hooks.state import WebHooksState
from src.utils.settings import WebHooksConfig


class WebHooksClient:
    """Stateful client for the webhooks interface, storing settings."""

    def __init__(self, state: WebHooksState, config: WebHooksConfig, secret_token: str):
        self.state = state
        self.config = config
        self.secret_token = secret_token

        self.state.host = config.host
        self.state.port = config.port

    async def get_context_block(self, **kwargs: Any) -> str:
        """Context provider block for the system prompt."""
        desc = "Description: Local HTTP server for receiving incoming webhooks."
        if not self.state.is_online:
            return f"### WEB HOOKS [OFF]\n{desc}\nThe interface is disabled."

        hooks_str = (
            "\n".join(self.state.preview_lines) if self.state.preview_lines else "  Empty."
        )

        return f"""
### WEB HOOKS [ON]
{desc}
* Server: http://{self.state.host}:{self.state.port}

* Endpoint for incoming requests: POST /webhook/{{source}} (where {{source}} is the name of the sending service)
* Authorization: '?token=' parameter or 'Authorization: Bearer' HTTP header

* Recent Webhooks:
{hooks_str}
"""

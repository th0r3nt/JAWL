"""
Stateful client of the custom interface.

All logic for connecting to the external world lives here (HTTP sessions, database connections,
authorization token management).

Developer Tips:
If your client needs helper functions (for example, parsing complex HTML
or formatting dates of a specific API), do not write them here.
Create a `src/l2_interfaces/your_name/utils.py` file and move the helper logic there (holy DRY).
"""

from typing import Any


class ExampleClient:
    """Connection manager for your service."""

    def __init__(self, state: Any, api_key: str) -> None:
        """
        Client initialization.

        Args:
            state: Reference to the L0 State from the agent's dashboard.
            api_key: Access key.
        """

        self.state = state
        self.api_key = api_key
        # self.session = None  # For example, aiohttp.ClientSession

    async def start(self) -> None:
        """
        Lifecycle method. Called by the orchestrator (main.py) when the system starts.
        Open HTTP sessions or make test requests (ping) to the API here.
        """

        # self.session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {self.api_key}"})
        self.state.is_online = True

    async def stop(self) -> None:
        """
        Lifecycle method. Called when the system shuts down.
        Safely close all sockets and release resources here.
        """
        
        # if self.session:
        #     await self.session.close()
        self.state.is_online = False

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Context provider. Called every time the agent wakes up (Heartbeat).

        Returns:
            str: Markdown-formatted text to be injected into the agent's System Prompt.
                 Try to keep it as short and informative as possible.
        """

        if not getattr(self.state, "is_online", False):
            return "### EXAMPLE_SERVICE [OFF]\nThe interface is disabled."

        # Pass cached (MRU) data from the state to the agent:
        # data = self.state.recent_notifications
        data = "No new notifications."

        return f"### EXAMPLE_SERVICE [ON]\n{data}"

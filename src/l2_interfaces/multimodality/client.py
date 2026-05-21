"""
Multimodality (Vision) interface client.

The interface itself is extremely simple, as the main magic occurs
during image injection in the ReAct loop (L3).
Here, we only initialize the availability marker and the context placeholder.
"""

from typing import Any
from src.l2_interfaces.host.os.client import HostOSClient


class MultimodalityClient:
    """
    Client for multimodal skills.
    Uses HostOSClient gatekeeper for safe access to image files.
    """

    def __init__(self, host_os_client: HostOSClient) -> None:
        """
        Initializes the client.

        Args:
            host_os_client: Initialized OS gatekeeper for path resolution.
        """

        self.host_os = host_os_client
        self.is_online = False

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Context provider for ContextRegistry.
        Returns a formatted context block for the agent.
        """

        desc = "Description: Processing and understanding images/screenshots."

        status = "ON" if self.is_online else "OFF"
        if not self.is_online:
            return f"### MULTIMODALITY [{status}]\n{desc}\nThe interface is disabled."

        return f"### MULTIMODALITY [{status}]\n{desc}\nMultimodal vision is active."

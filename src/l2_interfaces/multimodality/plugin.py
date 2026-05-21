"""
Multimodality (Vision) interface plugin.
"""

from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.multimodality.client import MultimodalityClient
from src.l2_interfaces.multimodality.skills.vision import VisionSkills
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class MultimodalityPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "MULTIMODALITY"

    @property
    def description(self) -> str:
        return "Processing and understanding images/screenshots."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.multimodality.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        if not getattr(container.settings.llm, "is_multimodal", False):
            main_logger.warning(
                "[Multimodality] Enabled, but llm.is_multimodal = False. Disabled."
            )
            self.register_off_provider(container.context_registry)
            return []

        os_state = container.l0_states.get("os") or HostOSState()

        host_os_client = HostOSClient(
            base_dir=container.root_dir,
            config=container.interfaces_config.host.os,
            state=os_state,
            timezone=container.settings.system.timezone,
        )

        client = MultimodalityClient(host_os_client=host_os_client)
        client.is_online = True

        register_instance(VisionSkills(client))

        container.context_registry.register_provider(
            "multimodality", client.get_context_block, ContextSection.INTERFACES
        )

        main_logger.info("[Multimodality] Agent gained vision (Plugin).")
        return []

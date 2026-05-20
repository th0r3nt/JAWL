from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.voice.tts.cloud.edge.state import CloudEdgeTTSState
from src.l2_interfaces.voice.tts.cloud.edge.voices import EdgeVoiceManager
from src.l2_interfaces.voice.tts.cloud.edge.client import EdgeClient
from src.l2_interfaces.voice.tts.cloud.edge.skills.generation import EdgeTTSGeneration
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class EdgePlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "EDGE TTS"

    @property
    def description(self) -> str:
        return "TTS generation via Microsoft Edge API."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.voice.tts.cloud.edge.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:

        state = CloudEdgeTTSState()
        container.l0_states["edge"] = state

        os_state = container.l0_states.get("os") or HostOSState()

        host_os_client = HostOSClient(
            base_dir=container.root_dir,
            config=container.interfaces_config.host.os,
            state=os_state,
            timezone=container.settings.system.timezone,
        )

        voice_manager = EdgeVoiceManager(container.interfaces_config.voice.tts.cloud.edge)

        client = EdgeClient(state=state, voice_manager=voice_manager)

        register_instance(EdgeTTSGeneration(client, host_os_client))

        container.context_registry.register_provider(
            "edge_tts", client.get_context_block, ContextSection.INTERFACES
        )

        main_logger.info("[Edge TTS] Загружен (Plugin).")
        return [client]

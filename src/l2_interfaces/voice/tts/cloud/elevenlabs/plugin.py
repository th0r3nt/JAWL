"""
ElevenLabs plugin for Telegram User API.
"""

from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.voice.tts.cloud.elevenlabs.state import CloudElevenLabsTTSState
from src.l2_interfaces.voice.tts.cloud.elevenlabs.voices import VoiceManager
from src.l2_interfaces.voice.tts.cloud.elevenlabs.client import CloudElevenLabsTTSClient
from src.l2_interfaces.voice.tts.cloud.elevenlabs.skills.generation import (
    CloudElevenLabsTTSGeneration,
)
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class ElevenLabsPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "ELEVENLABS TTS"

    @property
    def description(self) -> str:
        return "TTS generation via ElevenLabs API."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.voice.tts.cloud.elevenlabs.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:

        api_key = env_vars.get("ELEVENLABS_API_KEY")
        if not api_key:
            main_logger.error("[ElevenLabs] API key not specified. Disabled.")
            self.register_off_provider(container.context_registry)
            return []

        state = CloudElevenLabsTTSState()
        container.l0_states["elevenlabs"] = state

        os_state = container.l0_states.get("os") or HostOSState()

        host_os_client = HostOSClient(
            base_dir=container.root_dir,
            config=container.interfaces_config.host.os,
            state=os_state,
            timezone=container.settings.system.timezone,
        )

        voice_manager = VoiceManager(container.interfaces_config.voice.tts.cloud.elevenlabs)
        client = CloudElevenLabsTTSClient(
            state=state,
            voice_manager=voice_manager,
            api_key=api_key,
            api_url=env_vars.get("ELEVENLABS_API_URL", ""),
        )

        register_instance(CloudElevenLabsTTSGeneration(client, host_os_client))

        container.context_registry.register_provider(
            "elevenlabs_tts", client.get_context_block, ContextSection.INTERFACES
        )

        main_logger.info("[ElevenLabs] Loaded (Plugin).")
        return [client]

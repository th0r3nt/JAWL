"""
STT transcription via OpenAI Whisper interface plugin.
"""

from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.voice.stt.cloud.whisper.state import CloudWhisperSTTState
from src.l2_interfaces.voice.stt.cloud.whisper.client import CloudWhisperSTTClient
from src.l2_interfaces.voice.stt.cloud.whisper.skills.transcribation import (
    CloudWhisperSTTTranscribation,
)
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class WhisperPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "CLOUD WHISPER STT"

    @property
    def description(self) -> str:
        return "STT transcription via OpenAI Whisper."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.voice.stt.cloud.whisper.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:

        api_key = env_vars.get("CLOUD_WHISPER_API_KEY")
        if not api_key:
            main_logger.error("[Whisper STT] API key not specified. Disabled.")
            self.register_off_provider(container.context_registry)
            return []

        state = CloudWhisperSTTState()
        container.l0_states["cloud_whisper"] = state

        os_state = container.l0_states.get("os") or HostOSState()

        host_os_client = HostOSClient(
            base_dir=container.root_dir,
            config=container.interfaces_config.host.os,
            state=os_state,
            timezone=container.settings.system.timezone,
        )

        client = CloudWhisperSTTClient(
            state=state,
            config=container.interfaces_config.voice.stt.cloud.whisper,
            api_key=api_key,
            api_url=env_vars.get("CLOUD_WHISPER_API_URL"),
        )

        register_instance(CloudWhisperSTTTranscribation(client=client, host_os=host_os_client))

        container.context_registry.register_provider(
            "cloud_whisper_stt", client.get_context_block, ContextSection.INTERFACES
        )

        main_logger.info("[Whisper STT] Interface loaded.")
        return [client]

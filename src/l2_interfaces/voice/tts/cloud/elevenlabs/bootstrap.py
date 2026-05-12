"""
Инициализатор интерфейса ElevenLabs TTS.
"""

from typing import List, Any, TYPE_CHECKING

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.voice.tts.cloud.elevenlabs.voices import VoiceManager
from src.l2_interfaces.voice.tts.cloud.elevenlabs.client import CloudElevenLabsTTSClient
from src.l2_interfaces.voice.tts.cloud.elevenlabs.skills.generation import (
    CloudElevenLabsTTSGeneration,
)

if TYPE_CHECKING:
    from src.main import System


def setup_elevenlabs(system: "System", api_key: str, api_url: str) -> List[Any]:
    if not api_key:
        main_logger.error("[ElevenLabs] API ключ не задан. Интерфейс отключен.")
        return []

    host_os_client = HostOSClient(
        base_dir=system.root_dir,
        config=system.interfaces_config.host.os,
        state=system.os_state,
        timezone=system.settings.system.timezone,
    )

    config = system.interfaces_config.voice.tts.cloud.elevenlabs
    voice_manager = VoiceManager(config)

    # Берем стейт честно из DI-контейнера
    client = CloudElevenLabsTTSClient(
        state=system.elevenlabs_state,
        voice_manager=voice_manager,
        api_key=api_key,
        api_url=api_url,
    )

    register_instance(CloudElevenLabsTTSGeneration(client, host_os_client))

    system.context_registry.register_provider(
        name="elevenlabs_tts",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    main_logger.info("[ElevenLabs TTS] Интерфейс загружен.")
    return [client]

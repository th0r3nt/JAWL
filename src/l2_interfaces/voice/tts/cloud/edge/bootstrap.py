"""
Инициализатор интерфейса Edge TTS.

Внедряет зависимости, создает клиент, настраивает менеджер голосов
и регистрирует инструменты генерации речи в системном реестре навыков.
"""

from typing import List, Any, TYPE_CHECKING

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.voice.tts.cloud.edge.voices import EdgeVoiceManager
from src.l2_interfaces.voice.tts.cloud.edge.client import EdgeClient
from src.l2_interfaces.voice.tts.cloud.edge.skills.generation import EdgeTTSGeneration

if TYPE_CHECKING:
    from src.main import System


def setup_edge(system: "System") -> List[Any]:
    """
    Собирает и инициализирует Edge TTS.

    Args:
        system: Главный DI-контейнер фреймворка.

    Returns:
        List[Any]: Компоненты с жизненным циклом (client).
    """

    host_os_client = HostOSClient(
        base_dir=system.root_dir,
        config=system.interfaces_config.host.os,
        state=system.os_state,
        timezone=system.settings.system.timezone,
    )

    config = system.interfaces_config.voice.tts.cloud.edge
    voice_manager = EdgeVoiceManager(config)

    # Берем честно объявленный стейт из DI-контейнера
    client = EdgeClient(
        state=system.edge_state,
        voice_manager=voice_manager,
    )

    register_instance(EdgeTTSGeneration(client, host_os_client))

    system.context_registry.register_provider(
        name="edge_tts",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    main_logger.info("[Edge TTS] Интерфейс загружен.")
    return [client]

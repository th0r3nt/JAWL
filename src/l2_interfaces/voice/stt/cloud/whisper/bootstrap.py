"""
Инициализатор интерфейса Cloud Whisper STT.

Внедряет зависимости (DI), создает клиент, связывает его с гейткипером Host OS
и регистрирует инструмент транскрибации в системном реестре навыков.
"""

from typing import List, Any, TYPE_CHECKING, Optional

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.voice.stt.cloud.whisper.client import CloudWhisperSTTClient
from src.l2_interfaces.voice.stt.cloud.whisper.skills.transcribation import (
    CloudWhisperSTTTranscribation,
)

if TYPE_CHECKING:
    from src.main import System


def setup_cloud_whisper(
    system: "System", api_key: Optional[str], api_url: Optional[str]
) -> List[Any]:
    """
    Собирает и инициализирует Cloud Whisper.

    Args:
        system: Главный DI-контейнер фреймворка.
        api_key: Ключ API для OpenAI/совместимого API.
        api_url: Базовый URL.

    Returns:
        List[Any]: Компоненты с жизненным циклом (client).
    """

    if not api_key:
        main_logger.error("[Cloud Whisper STT] API ключ не задан. Интерфейс отключен.")
        return []

    # Создаем легковесный инстанс гейткипера для безопасного чтения файлов из песочницы
    host_os_client = HostOSClient(
        base_dir=system.root_dir,
        config=system.interfaces_config.host.os,
        state=system.os_state,
        timezone=system.settings.system.timezone,
    )

    config = system.interfaces_config.voice.stt.cloud.whisper

    client = CloudWhisperSTTClient(
        state=system.cloud_whisper_state,
        config=config,
        api_key=api_key,
        api_url=api_url,
    )

    register_instance(CloudWhisperSTTTranscribation(client=client, host_os=host_os_client))

    system.context_registry.register_provider(
        name="cloud_whisper_stt",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    main_logger.info("[Cloud Whisper STT] Интерфейс загружен.")
    return [client]

from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import register_instance
from src.l2_interfaces.host.os.client import HostOSClient

from src.l2_interfaces.multimodality.client import MultimodalityClient
from src.l2_interfaces.multimodality.skills.vision import VisionSkills

if TYPE_CHECKING:
    from src.main import System


def setup_multimodality(system: "System") -> List[Any]:
    """Инициализирует интерфейс Multimodality."""

    if not getattr(system.settings.llm, "is_multimodal", False):
        system_logger.warning(
            "[Multimodality] Интерфейс включен (multimodality: true), но модель "
            "не поддерживает зрение (llm.is_multimodal: false). Интерфейс принудительно отключен."
        )
        return []

    # Создаем легковесный инстанс гейткипера для проверки путей
    host_os_client = HostOSClient(
        base_dir=system.root_dir,
        config=system.interfaces_config.host.os,
        state=system.os_state,
        timezone=system.settings.system.timezone,
    )

    client = MultimodalityClient(host_os_client=host_os_client)

    # Регистрируем навыки
    register_instance(VisionSkills(client))

    system_logger.info("[Multimodality] Интерфейс загружен. Агент прозрел.")

    return []

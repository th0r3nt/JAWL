from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.events import HostOSEvents
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.skills.files import HostOSFiles
from src.l2_interfaces.host.os.skills.monitoring import HostOSMonitoring
from src.l2_interfaces.host.os.skills.network import HostOSNetwork
from src.l2_interfaces.host.os.skills.system import HostOSSystem

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection 

if TYPE_CHECKING:
    from src.main import System


def setup_host_os(system: "System") -> List[Any]:
    """Инициализирует Host OS, регистрирует скиллы и возвращает фоновые задачи (events)."""

    client = HostOSClient(
        base_dir=system.root_dir,
        config=system.interfaces_config.host.os,
        state=system.os_state,
        timezone=system.settings.system.timezone,
    )
    events = HostOSEvents(
        host_os_client=client, state=system.os_state, event_bus=system.event_bus
    )

    # Регистрация навыков для агента
    register_instance(HostOSExecution(client))
    register_instance(HostOSFiles(client))
    register_instance(HostOSNetwork(client))
    register_instance(HostOSSystem(client))
    register_instance(HostOSMonitoring(client, events))

    # Регистрация провайдеров контекста (отдают Markdown блоки в промпт агента)
    system.context_registry.register_provider(
            name="host os", provider_func=client.get_context_block, section=ContextSection.INTERFACES
        )

    system_logger.info("[Host OS] Интерфейс загружен.")

    # events имеет start() и stop() (Watchdog и поллинг)
    return [events]

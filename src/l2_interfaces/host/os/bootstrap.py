from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import register_instance

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.events import HostOSEvents
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.skills.files import HostOSFiles
from src.l2_interfaces.host.os.skills.monitoring import HostOSMonitoring
from src.l2_interfaces.host.os.skills.network import HostOSNetwork
from src.l2_interfaces.host.os.skills.system import HostOSSystem

if TYPE_CHECKING:
    from src.main import System


def setup_host_os(system: "System") -> List[Any]:
    """Инициализирует Host OS, регистрирует скиллы и возвращает фоновые задачи (events)."""

    os_client = HostOSClient(
        base_dir=system.root_dir,
        config=system.interfaces_config.host.os,
        state=system.os_state,
        timezone=system.settings.system.timezone,
    )
    os_events = HostOSEvents(
        host_os_client=os_client, state=system.os_state, event_bus=system.event_bus
    )

    # Регистрация навыков для агента
    register_instance(HostOSExecution(os_client))
    register_instance(HostOSFiles(os_client))
    register_instance(HostOSNetwork(os_client))
    register_instance(HostOSSystem(os_client))
    register_instance(HostOSMonitoring(os_client, os_events))

    system_logger.info("[System] Интерфейс Host OS загружен.")

    # os_events имеет start() и stop() (Watchdog и поллинг)
    return [os_events]

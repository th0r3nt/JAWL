"""
Инициализатор системного интерфейса Host OS.

Оркестрирует создание клиента (Гейткипера), регистрирует навыки взаимодействия с ОС
(сеть, процессы, деплой, файловая система) и поднимает фоновые воркеры (телеметрия, демоны, watchdog).
"""

from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.events import HostOSEvents
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.skills.monitoring import HostOSMonitoring
from src.l2_interfaces.host.os.skills.network import HostOSNetwork
from src.l2_interfaces.host.os.skills.desktop import HostOSDesktop
from src.l2_interfaces.host.os.skills.deploy import HostOSDeploy

# Импортируем наши новые распиленные файловые навыки
from src.l2_interfaces.host.os.skills.files.reader import HostOSReader
from src.l2_interfaces.host.os.skills.files.writer import HostOSWriter
from src.l2_interfaces.host.os.skills.files.editor import HostOSEditor
from src.l2_interfaces.host.os.skills.files.search import HostOSSearch
from src.l2_interfaces.host.os.skills.files.archive import HostOSArchive
from src.l2_interfaces.host.os.skills.files.workspace import HostOSWorkspace
from src.l2_interfaces.host.os.skills.files.metadata import HostOSMetadata

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_host_os(system: "System") -> List[Any]:
    """
    Инициализирует интерфейс Host OS.

    Args:
        system (System): Главный DI-контейнер фреймворка.

    Returns:
        List[Any]: Список фоновых задач (events), требующих запуска.
    """

    client = HostOSClient(
        base_dir=system.root_dir,
        config=system.interfaces_config.host.os,
        state=system.os_state,
        timezone=system.settings.system.timezone,
    )

    events = HostOSEvents(
        host_os_client=client, state=system.os_state, event_bus=system.event_bus
    )

    # Регистрация системных навыков
    register_instance(HostOSExecution(client))
    register_instance(HostOSNetwork(client))
    register_instance(HostOSMonitoring(client, events))
    register_instance(HostOSDeploy(client))

    # Регистрация файловых навыков (заменяет старый огромный HostOSFiles)
    register_instance(HostOSReader(client))
    register_instance(HostOSWriter(client))
    register_instance(HostOSEditor(client))
    register_instance(HostOSSearch(client))
    register_instance(HostOSArchive(client))
    register_instance(HostOSWorkspace(client))
    register_instance(HostOSMetadata(client))

    # Опциональная активация GUI-навыков
    if system.interfaces_config.host.os.desktop_interactions:
        register_instance(HostOSDesktop(client))

    # Регистрация провайдера контекста (отдает Markdown блок в промпт агента)
    system.context_registry.register_provider(
        name="host os",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Host OS] Интерфейс загружен.")

    # events содержит внутри себя агрегатор watchdog, телеметрии и демонов
    return [events]

"""
Host OS interface plugin.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.events import HostOSEvents

from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.skills.monitoring import HostOSMonitoring
from src.l2_interfaces.host.os.skills.network import HostOSNetwork
from src.l2_interfaces.host.os.skills.desktop import HostOSDesktop
from src.l2_interfaces.host.os.skills.deploy import HostOSDeploy
from src.l2_interfaces.host.os.skills.files.reader import HostOSReader
from src.l2_interfaces.host.os.skills.files.writer import HostOSWriter
from src.l2_interfaces.host.os.skills.files.editor import HostOSEditor
from src.l2_interfaces.host.os.skills.files.search import HostOSSearch
from src.l2_interfaces.host.os.skills.files.archive import HostOSArchive
from src.l2_interfaces.host.os.skills.files.workspace import HostOSWorkspace
from src.l2_interfaces.host.os.skills.files.metadata import HostOSMetadata
from src.l2_interfaces.host.os.skills.files.documents import HostOSDocuments

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class HostOsPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "HOST OS"

    @property
    def description(self) -> str:
        return "Host operating system access (files, processes, shell, network)."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.host.os.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        config = container.interfaces_config.host.os

        state = HostOSState()
        container.l0_states["os"] = state

        client = HostOSClient(
            base_dir=container.root_dir,
            config=config,
            state=state,
            timezone=container.settings.system.timezone,
        )

        events = HostOSEvents(
            host_os_client=client, state=state, event_bus=container.event_bus
        )

        register_instance(HostOSExecution(client))
        register_instance(HostOSNetwork(client))
        register_instance(HostOSMonitoring(client, events))
        register_instance(HostOSDeploy(client))
        register_instance(HostOSReader(client))
        register_instance(HostOSWriter(client))
        register_instance(HostOSEditor(client))
        register_instance(HostOSSearch(client))
        register_instance(HostOSArchive(client))
        register_instance(HostOSWorkspace(client))
        register_instance(HostOSMetadata(client))
        register_instance(HostOSDocuments(client))

        if config.desktop_interactions:
            register_instance(HostOSDesktop(client))

        container.context_registry.register_provider(
            name="host_os",
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Host OS] Interface loaded.")
        return [events]

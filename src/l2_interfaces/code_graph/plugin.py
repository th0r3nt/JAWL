"""
Code Graph (Playwright) interface plugin.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.code_graph.state import CodeGraphState
from src.l2_interfaces.code_graph.client import CodeGraphClient
from src.l2_interfaces.code_graph.skills.indexing import CodeGraphIndexing
from src.l2_interfaces.code_graph.skills.navigation import CodeGraphNavigation

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class CodeGraphPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "CODE GRAPH"

    @property
    def description(self) -> str:
        return "Parsing Python directory AST-trees and constructing dependency/relationship graphs for semantic search."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return getattr(config, "code_graph", None) and getattr(
            config.code_graph, "enabled", False
        )

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        os_state = container.l0_states.get("os") or HostOSState()

        host_os_client = HostOSClient(
            base_dir=container.root_dir,
            config=container.interfaces_config.host.os,
            state=os_state,
            timezone=container.settings.system.timezone,
        )

        state = CodeGraphState(data_dir=container.local_data_dir)
        container.l0_states["code_graph"] = state

        config = container.interfaces_config.code_graph
        client = CodeGraphClient(state=state, config=config, host_os=host_os_client)

        register_instance(
            CodeGraphIndexing(client, container.graph.ast_crud, container.vector.code_ast)
        )
        register_instance(
            CodeGraphNavigation(client, container.graph.ast_crud, container.vector.code_ast)
        )

        container.context_registry.register_provider(
            name="code_graph",
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info("[Code Graph] Interface loaded.")
        return []

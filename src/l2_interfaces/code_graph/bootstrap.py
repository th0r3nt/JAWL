"""
Инициализирует интерфейс Code Graph.

Кодовые графы хранят зависимости, описания и помогают разбираться в сложных кодовых базах,
благодаря векторному поиску по связям в детерминированном графе.
"""

from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.code_graph.client import CodeGraphClient
from src.l2_interfaces.code_graph.skills.indexing import CodeGraphIndexing
from src.l2_interfaces.code_graph.skills.navigation import CodeGraphNavigation

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_code_graph(system: "System") -> List[Any]:
    """
    Инициализирует интерфейс Code Graph.
    """

    # Нам нужен гейткипер ОС для безопасного чтения файлов при парсинге
    host_os_client = HostOSClient(
        base_dir=system.root_dir,
        config=system.interfaces_config.host.os,
        state=system.os_state,
        timezone=system.settings.system.timezone,
    )

    if not hasattr(system, "code_graph_state"):
        from src.l2_interfaces.code_graph.state import CodeGraphState

        system.code_graph_state = CodeGraphState(data_dir=system.local_data_dir)

    client = CodeGraphClient(state=system.code_graph_state, host_os=host_os_client)

    # Регистрируем навыки
    register_instance(CodeGraphIndexing(client, system.graph.ast_crud, system.vector.code_ast))
    register_instance(
        CodeGraphNavigation(client, system.graph.ast_crud, system.vector.code_ast)
    )

    system.context_registry.register_provider(
        name="code_graph",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Code Graph] Интерфейс загружен.")
    return []

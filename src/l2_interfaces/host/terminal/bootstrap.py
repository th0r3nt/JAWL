from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

from src.l2_interfaces.host.terminal.client import HostTerminalClient
from src.l2_interfaces.host.terminal.events import HostTerminalEvents
from src.l2_interfaces.host.terminal.skills.messages import HostTerminalMessages

if TYPE_CHECKING:
    from src.main import System


def setup_host_terminal(system: "System") -> List[Any]:
    config = system.interfaces_config.host.terminal

    # Инициализируем клиент
    client = HostTerminalClient(
        state=system.terminal_state,
        config=config,
        data_dir=system.local_data_dir,
        agent_name=system.settings.identity.agent_name,
        timezone=system.settings.system.timezone,
    )

    # Инициализируем фоновый воркер
    events = HostTerminalEvents(client=client, event_bus=system.event_bus)

    # Регистрируем навык для агента
    register_instance(HostTerminalMessages(client))

    # Регистрируем блок в системный промпт
    system.context_registry.register_provider(
        name="host terminal",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Host Terminal] Bнтерфейс загружен.")

    # Возвращаем компоненты с жизненным циклом start()/stop()
    return [client, events]

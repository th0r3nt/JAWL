from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import register_instance

from src.l2_interfaces.meta.client import MetaClient
from src.l2_interfaces.meta.skills.configuration import MetaConfiguration
from src.l2_interfaces.meta.skills.system import MetaSystem

if TYPE_CHECKING:
    from src.main import System


def setup_meta(system: "System") -> List[Any]:
    """Инициализирует интерфейс Meta. Фоновых процессов нет."""
    
    settings_path = system.root_dir / "config" / "settings.yaml"
    client = MetaClient(
        agent_state=system.agent_state, 
        event_bus=system.event_bus, 
        settings_path=settings_path
    )

    # Регистрация навыков для агента
    register_instance(MetaConfiguration(client))
    register_instance(MetaSystem(client))

    # Регистрация провайдеров контекста (отдают Markdown блоки в промпт агента)
    system.context_registry.register_provider(name="meta", provider_func=client.get_context_block)

    system_logger.info("[System] Интерфейс Meta загружен.")
    
    return []
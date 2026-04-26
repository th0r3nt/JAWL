from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger
from src.l2_interfaces.meta.client import MetaClient

from src.l2_interfaces.meta.skills.level_safe import MetaSafe
from src.l2_interfaces.meta.skills.level_configurator import MetaConfigurator
from src.l2_interfaces.meta.skills.level_architect import MetaArchitect

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System

def setup_meta(system: "System") -> List[Any]:
    settings_path = system.root_dir / "config" / "settings.yaml"
    interfaces_path = system.root_dir / "config" / "interfaces.yaml"
    
    meta_config = system.interfaces_config.meta
    
    client = MetaClient(
        agent_state=system.agent_state, 
        event_bus=system.event_bus, 
        settings_path=settings_path,
        interfaces_path=interfaces_path,
        access_level=meta_config.access_level,
        available_models=system.settings.llm.available_models
    )

    # Динамическая регистрация навыков по уровням доступа
    # 0 (SAFE) регистрируется в любом случае, если интерфейс включен
    register_instance(MetaSafe(client))
    
    if meta_config.access_level >= 1:
        register_instance(MetaConfigurator(client, system.root_dir))
        
    if meta_config.access_level >= 2:
        register_instance(MetaArchitect(client))

    system.context_registry.register_provider(
        name="meta", provider_func=client.get_context_block, section=ContextSection.INTERFACES
    )
    
    system_logger.info(f"[Meta] Интерфейс загружен (Access Level: {meta_config.access_level}).")
    return []
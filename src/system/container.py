"""
Контейнер зависимостей системы JAWL.
Глупый дата-класс без бизнес-логики. Служит единым хранилищем для всех
инициализированных компонентов, сгруппированных по слоям (L0-L3).
"""

from pathlib import Path
from typing import Dict, List, Any, Optional

from src.utils.settings import SettingsConfig, InterfacesConfig
from src.utils.event.bus import EventBus

from src.l0_state.agent.state import AgentState

from src.l1_databases.sql.manager import SQLManager
from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.graph.manager import GraphManager

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.heartbeat import Heartbeat
from src.l3_agent.context.registry import ContextRegistry


class SystemContainer:
    """Хранилище собранных деталей системы."""

    def __init__(
        self,
        settings: SettingsConfig,
        interfaces_config: InterfacesConfig,
        event_bus: EventBus,
    ) -> None:
        # Глобальные зависимости
        self.settings = settings
        self.interfaces_config = interfaces_config
        self.event_bus = event_bus

        self.root_dir = Path.cwd()
        self.local_data_dir = self.root_dir / "src" / "utils" / "local" / "data"
        self.exit_code: int = 0

        # L0 State
        self.agent_state: Optional[AgentState] = None
        self.l0_states: Dict[str, Any] = {}  # Из файлов state.py в папках l2_interfaces

        # L1 Databases
        self.sql: Optional[SQLManager] = None
        self.vector: Optional[VectorManager] = None
        self.graph: Optional[GraphManager] = None

        # L2 Interfaces
        self.l2_clients: Dict[str, Any] = {}
        self.lifecycle_components: List[Any] = []

        # L3 Agent
        self.llm_client: Optional[LLMClient] = None
        self.sub_llm_client: Optional[LLMClient] = None
        self.heartbeat: Optional[Heartbeat] = None
        self.context_registry: Optional[ContextRegistry] = None
        self.subconscious_orchestrator: Optional[Any] = None

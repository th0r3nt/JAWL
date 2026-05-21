"""
Abstract contract for all L2 interfaces (Plugin Pattern).

Provides loose coupling between the system core and modules.
The core knows nothing about specific implementations; it simply scans the directory,
finds heirs of BaseInterface, and invokes their methods according to the contract.
"""

from abc import ABC, abstractmethod
from typing import List, Any, Dict, Optional, TYPE_CHECKING

from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.system.container import SystemContainer
    from src.utils.settings import InterfacesConfig
    from src.l3_agent.context.registry import ContextRegistry


class BaseInterface(ABC):
    """
    Base class (contract) for all L2 plugins.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable interface name (e.g., 'WEB HTTP')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of functionality for the system prompt."""
        pass

    @abstractmethod
    def is_enabled(self, config: "InterfacesConfig") -> bool:
        """
        Checks in the global configuration if this interface is enabled.

        Args:
            config: Global configuration of interfaces.

        Returns:
            bool: True if the plugin is activated by the user.
        """
        pass

    @abstractmethod
    def setup(
        self, container: "SystemContainer", env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        """
        Main initialization method for the plugin.
        States, clients, and workers are created here, and skills (Skills)
        and context providers (Context Providers) are registered.

        Args:
            container: System DI container (contains event_bus, data_dir, etc.).
            env_vars: Dictionary of secrets from .env.

        Returns:
            List[Any]: List of lifecycle components (clients, pollers),
                       on which the Orchestrator will later call start() and stop().
        """
        pass

    def register_off_provider(self, context_registry: "ContextRegistry") -> None:
        """
        Registers an [OFF] placeholder in the context registry if the interface is disabled.
        This is a system method that does not need to be overridden in plugins.

        Args:
            context_registry: Agent context registry.
        """

        async def off_provider(**kwargs: Any) -> str:
            return f"### {self.name} [OFF]\nDescription: {self.description}\nThe interface is disabled in .yaml configuration."

        # Register the placeholder using the interface name as a unique key
        registry_name = self.name.lower().replace(" ", "_")
        context_registry.register_provider(
            name=registry_name,
            provider_func=off_provider,
            section=ContextSection.INTERFACES,
        )

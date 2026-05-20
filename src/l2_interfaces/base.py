"""
Абстрактный контракт для всех L2-интерфейсов (Паттерн Plugin).

Обеспечивает слабую связность (Loose Coupling) между ядром системы и модулями.
Ядро не знает о конкретных реализациях, оно просто сканирует директорию, 
находит наследников BaseInterface и вызывает их методы согласно контракту.
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
    Базовый класс (контракт) для всех L2 плагинов.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Человекочитаемое имя интерфейса (например, 'WEB HTTP')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Краткое описание функционала для системного промпта."""
        pass

    @abstractmethod
    def is_enabled(self, config: "InterfacesConfig") -> bool:
        """
        Проверяет в глобальной конфигурации, включен ли данный интерфейс.
        
        Args:
            config: Глобальный конфиг интерфейсов.
            
        Returns:
            bool: True, если плагин активирован пользователем.
        """
        pass

    @abstractmethod
    def setup(self, container: "SystemContainer", env_vars: Dict[str, Optional[str]]) -> List[Any]:
        """
        Главный метод инициализации плагина.
        Здесь создаются стейты, клиенты, воркеры, регистрируются навыки (Skills)
        и провайдеры контекста (Context Providers).
        
        Args:
            container: DI-контейнер системы (содержит event_bus, data_dir и т.д.).
            env_vars: Словарь секретов из .env.
            
        Returns:
            List[Any]: Список компонентов жизненного цикла (клиенты, поллеры),
                       у которых Оркестратор позже вызовет start() и stop().
        """
        pass

    def register_off_provider(self, context_registry: "ContextRegistry") -> None:
        """
        Регистрирует заглушку [OFF] в контекстном реестре, если интерфейс выключен.
        Это системный метод, который не нужно переопределять в плагинах.
        
        Args:
            context_registry: Реестр контекста агента.
        """
        async def off_provider(**kwargs: Any) -> str:
            return f"### {self.name} [OFF]\nDescription: {self.description}\nThe interface is disabled in .yaml configuration."

        # Регистрируем заглушку, используя имя интерфейса как уникальный ключ
        registry_name = self.name.lower().replace(" ", "_")
        context_registry.register_provider(
            name=registry_name,
            provider_func=off_provider,
            section=ContextSection.INTERFACES,
        )
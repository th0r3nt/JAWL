"""
Клиент интерфейса мультимодальности (Зрения).

Сам по себе интерфейс крайне прост, так как основная магия происходит
во время инъекции изображений в ReAct-цикле (L3).
Здесь же инициализируется лишь маркер доступности и заглушка контекста.
"""

from typing import Any
from src.l2_interfaces.host.os.client import HostOSClient


class MultimodalityClient:
    """
    Клиент для мультимодальных навыков.
    Использует гейткипер HostOSClient для безопасного доступа к файлам изображений.
    """

    def __init__(self, host_os_client: HostOSClient) -> None:
        """
        Инициализирует клиент.

        Args:
            host_os_client: Инициализированный гейткипер ОС для резолва путей.
        """

        self.host_os = host_os_client
        self.is_online = False

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок контекста для агента.
        """
        
        status = "ON" if self.is_online else "OFF"
        if not self.is_online:
            return f"### MULTIMODALITY [{status}]\nИнтерфейс отключен."

        return f"### MULTIMODALITY [{status}]\nМультимодальное зрение активно."

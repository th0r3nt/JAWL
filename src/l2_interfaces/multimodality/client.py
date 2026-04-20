from src.l2_interfaces.host.os.client import HostOSClient


class MultimodalityClient:
    """
    Клиент для мультимодальных навыков.
    Использует гейткипер HostOSClient для безопасного доступа к файлам.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client
        self.is_online = False

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок контекста для агента.
        """

        status = "ON" if self.is_online else "OFF"
        if not self.is_online:
            return f"### MULTIMODALITY [{status}]\nИнтерфейс отключен."

        return f"### MULTIMODALITY [{status}]\nМультимодальное зрение активно."

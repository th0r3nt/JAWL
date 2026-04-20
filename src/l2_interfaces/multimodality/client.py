from src.l2_interfaces.host.os.client import HostOSClient


class MultimodalityClient:
    """
    Клиент для мультимодальных навыков.
    Использует гейткипер HostOSClient для безопасного доступа к файлам.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

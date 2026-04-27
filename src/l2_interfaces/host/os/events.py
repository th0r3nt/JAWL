from src.utils.event.bus import EventBus
from src.utils.logger import system_logger

from src.l0_state.interfaces.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient

from src.l2_interfaces.host.os.polls.telemetry import TelemetryPoller
from src.l2_interfaces.host.os.polls.daemons import DaemonsPoller
from src.l2_interfaces.host.os.polls.file_watcher import FileWatcher


class HostOSEvents:
    """
    Фасад для управления фоновыми воркерами Host OS.
    Оркестрирует поллеры телеметрии, демонов и файловой системы.
    """

    def __init__(self, host_os_client: HostOSClient, state: HostOSState, event_bus: EventBus):
        self.client = host_os_client
        self.state = state
        self.bus = event_bus

        # Инициализируем специализированные воркеры
        self.telemetry = TelemetryPoller(client=self.client, state=self.state)
        self.daemons = DaemonsPoller(client=self.client, state=self.state, bus=self.bus)
        self.files = FileWatcher(client=self.client, state=self.state, bus=self.bus)

    async def start(self) -> None:
        """
        Запускает всех воркеров.
        """

        self.telemetry.start()
        self.daemons.start()
        self.files.start()
        system_logger.info("[Host OS] Мониторинги запущены.")

    async def stop(self) -> None:
        """
        Корректно останавливает всех воркеров.
        """

        self.telemetry.stop()
        self.daemons.stop()
        await self.files.stop()

        system_logger.info("[Host OS] Мониторинг остановлен.")
        self.state.is_online = False

    # ==========================================================
    # ДЕЛЕГИРОВАНИЕ МЕТОДОВ ДЛЯ НАВЫКОВ АГЕНТА
    # Эти методы вызываются из HostOSMonitoring (skills/monitoring.py)
    # ==========================================================

    def track_path(self, path_str: str, save: bool = True) -> bool:
        return self.files.track_path(path_str, save=save)

    def untrack_path(self, path_str: str) -> bool:
        return self.files.untrack_path(path_str)

    @property
    def _watches(self):
        """Необходимо для навыка get_tracked_directories."""
        return self.files._watches

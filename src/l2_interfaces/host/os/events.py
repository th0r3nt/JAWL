"""
Facade for managing Host OS background workers.

Orchestrates telemetry, daemon, and file system pollers.
"""

from src.utils.event.bus import EventBus
from src.utils.logger import main_logger

from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient

from src.l2_interfaces.host.os.polls.telemetry import TelemetryPoller
from src.l2_interfaces.host.os.polls.daemons import DaemonsPoller
from src.l2_interfaces.host.os.polls.file_watcher import FileWatcher


class HostOSEvents:
    """
    Facade for managing Host OS background workers.
    Orchestrates telemetry, daemon, and file system pollers.
    """

    def __init__(self, host_os_client: HostOSClient, state: HostOSState, event_bus: EventBus):
        self.client = host_os_client
        self.state = state
        self.bus = event_bus

        # Initialize specialized workers
        self.telemetry = TelemetryPoller(client=self.client, state=self.state)
        self.daemons = DaemonsPoller(client=self.client, state=self.state, bus=self.bus)
        self.files = FileWatcher(client=self.client, state=self.state, bus=self.bus)

    async def start(self) -> None:
        """
        Starts all workers.
        """

        self.telemetry.start()
        self.daemons.start()
        self.files.start()
        main_logger.info("[Host OS] Monitors started.")

    async def stop(self) -> None:
        """
        Correctly stops all workers.
        """

        self.telemetry.stop()
        self.daemons.stop()
        await self.files.stop()

        main_logger.info("[Host OS] Monitoring stopped.")
        self.state.is_online = False

    # ==========================================================
    # DELEGATING METHODS FOR AGENT SKILLS
    # These methods are called from HostOSMonitoring (skills/monitoring.py)
    # ==========================================================

    def track_path(self, path_str: str, save: bool = True) -> bool:
        return self.files.track_path(path_str, save=save)

    def untrack_path(self, path_str: str) -> bool:
        return self.files.untrack_path(path_str)

    @property
    def _watches(self):
        """Required for get_tracked_directories skill."""
        return self.files._watches

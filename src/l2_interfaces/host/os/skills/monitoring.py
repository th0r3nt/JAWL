"""
Skills for managing tracked directories (Watchdog).
"""

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l2_interfaces.host.os.events import HostOSEvents

from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class HostOSMonitoring:
    """Skills for managing watchdog-tracked directories."""

    def __init__(self, host_os_client: HostOSClient, host_os_events: HostOSEvents):
        self.host_os = host_os_client
        self.events = host_os_events

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def track_directory(self, path: str) -> SkillResult:
        """
        Starts tracking directory changes (creates/deletes/modifications).
        Pins file tree.
        Highly recommended for keeping structure visible.
        """
        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            success = self.events.track_path(str(safe_path))
            if not success:
                return SkillResult.ok("True")

            main_logger.info(f"[Host OS] Started tracking directory: {safe_path}")
            return SkillResult.ok("True")

        except ValueError as e:
            return SkillResult.fail(str(e))

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error adding tracking: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def untrack_directory(self, path: str) -> SkillResult:
        """
        Stops directory tracking.
        """

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)
            success = self.events.untrack_path(str(safe_path))

            if not success:
                return SkillResult.fail(f"Error: Directory {safe_path.name} is not tracked.")

            main_logger.info(f"[Host OS] Stopped tracking directory: {safe_path}")
            return SkillResult.ok("True")

        except ValueError as e:
            return SkillResult.fail(str(e))
        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error removing tracking: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def get_tracked_directories(self) -> SkillResult:
        """
        Returns list of tracked directories.
        """

        tracked = list(self.events._watches.keys())

        if not tracked:
            return SkillResult.ok("Tracked directories list is empty.")

        lines = ["Tracked directories:"]
        for p in tracked:
            lines.append(f"- {p}")

        return SkillResult.ok("\n".join(lines))

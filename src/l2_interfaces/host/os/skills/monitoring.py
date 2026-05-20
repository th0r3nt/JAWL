from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l2_interfaces.host.os.events import HostOSEvents

from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class HostOSMonitoring:
    """Навыки для управления отслеживаемыми директориями (Watchdog)."""

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
            # Гейткипер проверит, имеет ли агент права на чтение этой папки
            safe_path = self.host_os.validate_path(path, is_write=False)

            success = self.events.track_path(str(safe_path))
            if not success:
                return SkillResult.ok("True")

            main_logger.info(f"[Host OS] Начато отслеживание директории: {safe_path}")
            return SkillResult.ok("True")

        except ValueError as e:
            return SkillResult.fail(str(e))

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при добавлении отслеживания: {e}")

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
                return SkillResult.fail(
                    f"Ошибка: Директория {safe_path.name} не отслеживается."
                )

            main_logger.info(f"[Host OS] Прекращено отслеживание директории: {safe_path}")
            return SkillResult.ok("True")

        except ValueError as e:
            return SkillResult.fail(str(e))
        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении отслеживания: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def get_tracked_directories(self) -> SkillResult:
        """
        Returns list of tracked directories.
        """

        tracked = list(self.events._watches.keys())

        if not tracked:
            return SkillResult.ok("Список отслеживаемых директорий пуст.")

        lines = ["Отслеживаемые директории:"]
        for p in tracked:
            lines.append(f"- {p}")

        return SkillResult.ok("\n".join(lines))

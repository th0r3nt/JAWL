from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.events import HostOSEvents

from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class HostOSMonitoring:
    """Навыки для управления отслеживаемыми директориями (Watchdog)."""

    def __init__(self, host_os_client: HostOSClient, host_os_events: HostOSEvents):
        self.host_os = host_os_client
        self.events = host_os_events

    @skill()
    async def track_directory(self, path: str) -> SkillResult:
        """Начинает отслеживание изменений в указанной директории (создание, удаление, изменение файлов)."""
        try:
            # Гейткипер проверит, имеет ли агент права на чтение этой папки
            safe_path = self.host_os.validate_path(path, is_write=False)

            success = self.events.track_path(str(safe_path))
            if not success:
                return SkillResult.ok(f"Директория {safe_path.name} уже отслеживается.")

            system_logger.info(f"[Host OS] Начато отслеживание директории: {safe_path}")
            return SkillResult.ok(f"Успешно. Директория {safe_path} теперь отслеживается.")

        except ValueError as e:
            return SkillResult.fail(str(e))
        
        except PermissionError as e:
            return SkillResult.fail(str(e))
        
        except Exception as e:
            return SkillResult.fail(f"Ошибка при добавлении отслеживания: {e}")

    @skill()
    async def untrack_directory(self, path: str) -> SkillResult:
        """Прекращает отслеживание директории."""
        try:
            safe_path = self.host_os.validate_path(path, is_write=False)
            success = self.events.untrack_path(str(safe_path))

            if not success:
                return SkillResult.fail(
                    f"Ошибка: Директория {safe_path.name} не отслеживается."
                )

            system_logger.info(f"[Host OS] Прекращено отслеживание директории: {safe_path}")
            return SkillResult.ok(f"Успешно. Директория {safe_path} больше не отслеживается.")

        except ValueError as e:
            return SkillResult.fail(str(e))
        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении отслеживания: {e}")

    @skill()
    async def get_tracked_directories(self) -> SkillResult:
        """Возвращает список всех отслеживаемых директорий."""
        tracked = list(self.events._watches.keys())

        if not tracked:
            return SkillResult.ok("Список отслеживаемых директорий пуст.")

        lines = ["Отслеживаемые директории:"]
        for p in tracked:
            lines.append(f"- {p}")

        return SkillResult.ok("\n".join(lines))

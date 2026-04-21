import sys
from enum import IntEnum
from pathlib import Path

from src.utils.logger import system_logger
from src.utils.settings import HostOSConfig
from src.l0_state.interfaces.state import HostOSState


class HostOSAccessLevel(IntEnum):
    SANDBOX = 0  # Read/Write только внутри sandbox/
    OBSERVER = 1  # Read фреймворка, Write в sandbox/
    OPERATOR = 2  # Read всей ОС, Write только внутри фреймворка (может менять свой код)
    ROOT = 3  # Полный Read/Write по всей системе


class HostOSClient:
    def __init__(
        self, base_dir: Path | str, config: HostOSConfig, state: HostOSState, timezone: int
    ):
        self.config = config
        self.state = state
        self.timezone = timezone

        try:
            self.access_level = HostOSAccessLevel(self.config.access_level)
        except ValueError:
            system_logger.warning(
                f"[Host OS] Неизвестный access_level: {self.config.access_level}. Сброс на SANDBOX (0)."
            )
            self.access_level = HostOSAccessLevel.SANDBOX

        self.os_platform = sys.platform

        self.framework_dir = Path(base_dir).resolve()
        self.sandbox_dir = self.framework_dir / "sandbox"

        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

        system_logger.info(
            f"[Host OS] Клиент инициализирован (ОС: {self.os_platform}, Access Level: {self.access_level.name})."
        )
        self.state.is_online = True

    def validate_path(self, target_path: str | Path, is_write: bool = False) -> Path:
        """
        Проверяет переданный путь на безопасность
        + уровни доступа агента к файловой системе.
        """

        path_obj = Path(target_path)

        # Smart Resolve: если путь относительный,
        # резолвим его относительно песочницы, очищая от дубликатов "sandbox/"
        if not path_obj.is_absolute():
            path_str = str(path_obj).replace("\\", "/")
            if path_str.startswith("sandbox/"):
                path_str = path_str[8:]  # Отрезаем префикс "sandbox/"
            resolved_path = (self.sandbox_dir / path_str).resolve()
        else:
            resolved_path = path_obj.resolve()

        if not self.config.env_access and ".env" in resolved_path.name.lower():
            raise PermissionError(
                f"SYSTEM DENIED: Доступ к файлам конфигурации ({resolved_path.name}) запрещен."
            )

        if self.access_level == HostOSAccessLevel.ROOT:
            return resolved_path

        if self.access_level == HostOSAccessLevel.OPERATOR:
            if is_write and not resolved_path.is_relative_to(self.framework_dir):
                raise PermissionError("OPERATOR: Запись разрешена только в директории JAWL.")
            
            return resolved_path

        if self.access_level == HostOSAccessLevel.OBSERVER:
            if is_write and not resolved_path.is_relative_to(self.sandbox_dir):
                raise PermissionError("OBSERVER: Запись разрешена строго в папке sandbox/.")
            
            if not is_write and not resolved_path.is_relative_to(self.framework_dir):
                raise PermissionError("OBSERVER: Чтение разрешено только в пределах JAWL.")
            
            return resolved_path

        if not resolved_path.is_relative_to(self.sandbox_dir):
            raise PermissionError(
                f"SANDBOX: Доступ разрешен строго внутри sandbox/. Путь '{resolved_path}' отклонен."
            )

        return resolved_path

    async def get_context_block(self, **kwargs) -> str:

        if not self.state.is_online:
            return "### HOST OS [OFF]\nИнтерфейс отключен."

        return f"""### HOST OS [ON]
* OS: {self.state.os_info}
* Access Level: {self.access_level.value} ({self.access_level.name}) / 3
* Datetime: {self.state.datetime}
* Uptime: {self.state.uptime}
* Network: {getattr(self.state, 'network', 'Неизвестно')}

{self.state.telemetry}

* Sandbox Directory:
{self.state.sandbox_files}""".strip()

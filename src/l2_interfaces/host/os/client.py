import sys
import json
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

        # Файл для реестра описаний файлов
        self.metadata_file = (
            self.framework_dir
            / "src"
            / "utils"
            / "local"
            / "data"
            / "host os"
            / "file_meta.json"
        )
        self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.metadata_file.exists():
            self.metadata_file.write_text("{}", encoding="utf-8")

    def validate_path(self, target_path: str | Path, is_write: bool = False) -> Path:
        """
        Умный гейткипер. Парсит пути так, как их видит агент в дереве контекста,
        и проверяет права доступа.
        """
        path_str = str(target_path).replace("\\", "/").strip()
        path_obj = Path(path_str)

        # Если путь абсолютный - оставляем как есть
        if path_obj.is_absolute():
            resolved_path = path_obj.resolve()

        else:
            # Делегируем сложность скрипту (умный резолв)
            fw_name = self.framework_dir.name  # Обычно "JAWL"

            if path_str.startswith(f"{fw_name}/"):
                # Агент пишет "JAWL/docs/TODO.md" -> ищем в корне фреймворка
                sub_path = path_str[len(fw_name) + 1 :]
                resolved_path = (self.framework_dir / sub_path).resolve()

            elif path_str == fw_name:
                resolved_path = self.framework_dir.resolve()

            elif path_str.startswith("sandbox/"):
                # Агент пишет "sandbox/test.txt" -> ищем в песочнице
                sub_path = path_str[8:]
                resolved_path = (self.sandbox_dir / sub_path).resolve()

            elif path_str in [".", "./"]:
                # Текущая папка по умолчанию - песочница
                resolved_path = self.sandbox_dir.resolve()

            elif path_str in ["..", "../"]:
                # Подняться на уровень выше - корень фреймворка
                resolved_path = self.framework_dir.resolve()

            else:
                # Умный fallback: "Do What I Mean"
                sandbox_target = (self.sandbox_dir / path_str).resolve()
                fw_target = (self.framework_dir / path_str).resolve()
                
                # Если в песочнице запрошенного пути нет, но он физически существует во фреймворке
                if not sandbox_target.exists() and fw_target.exists() and self.access_level >= HostOSAccessLevel.OBSERVER:
                    if is_write and self.access_level == HostOSAccessLevel.OBSERVER:
                        resolved_path = sandbox_target
                    else:
                        resolved_path = fw_target
                else:
                    # Во всех остальных случаях считаем, что агент работает в песочнице
                    resolved_path = sandbox_target

        # Проверка прав доступа
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

    def get_file_metadata(self) -> dict:
        """Читает реестр описаний файлов."""

        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def set_file_metadata(self, rel_path: str, description: str) -> None:
        """Сохраняет описание для конкретного файла."""

        data = self.get_file_metadata()
        data[rel_path] = description
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    async def get_context_block(self, **kwargs) -> str:

        if not self.state.is_online:
            return "### HOST OS [OFF]\nИнтерфейс отключен."

        framework_block = ""
        if self.access_level >= HostOSAccessLevel.OBSERVER and self.state.framework_files:
            framework_block = f"\n\n* JAWL Directory:\n{self.state.framework_files}"

        return f"""### HOST OS [ON]
* OS: {self.state.os_info}
* Access Level: {self.access_level.value} ({self.access_level.name}) / 3
* Polling interval: {self.state.polling_interval}
* Datetime: {self.state.datetime}
* Uptime: {self.state.uptime}
* Network: {getattr(self.state, 'network', 'Неизвестно')}

{self.state.telemetry}

* Sandbox Directory:
{self.state.sandbox_files}{framework_block}""".strip()

import sys
from enum import IntEnum
from pathlib import Path

from src.utils.logger import system_logger
from src.utils.settings import HostOSConfig


class MadnessLevel(IntEnum):
    CAGE = 0  # Read/Write только внутри sandbox/
    VOYEUR = 1  # Read фреймворка, Write в sandbox/
    SURGEON = 2  # Read всей ОС, Write только внутри фреймворка (может менять свой код)
    GOD_MODE = 3  # Полный Read/Write по всей системе


class HostOSClient:
    """
    Базовый клиент интерфейса Host OS.
    Выступает в роли Гейткипера (проверка прав доступа).
    """

    def __init__(self, base_dir: Path | str, config: HostOSConfig):
        self.config = config

        try:
            self.madness_level = MadnessLevel(self.config.madness_level)
        except ValueError:
            system_logger.warning(
                f"[Host OS] Неизвестный madness_level: {self.config.madness_level}. Сброс на CAGE (0)."
            )
            self.madness_level = MadnessLevel.CAGE

        self.os_platform = sys.platform

        # Внедрение зависимости: явно задаем корень без жесткой привязки к расположению файла
        self.framework_dir = Path(base_dir).resolve()
        self.sandbox_dir = self.framework_dir / "sandbox"

        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

        system_logger.info(
            f"[Host OS] Клиент инициализирован (ОС: {self.os_platform}, Madness: {self.madness_level.name})."
        )

    def validate_path(self, target_path: str | Path, is_write: bool = False) -> Path:
        resolved_path = Path(target_path).resolve()

        if self.madness_level == MadnessLevel.GOD_MODE:
            return resolved_path

        if self.madness_level == MadnessLevel.SURGEON:
            if is_write and not resolved_path.is_relative_to(self.framework_dir):
                raise PermissionError("SURGEON: Запись разрешена только в директории JAWL.")
            return resolved_path

        if self.madness_level == MadnessLevel.VOYEUR:

            if is_write and not resolved_path.is_relative_to(self.sandbox_dir):
                raise PermissionError("VOYEUR: Запись разрешена строго в папке sandbox/.")

            if not is_write and not resolved_path.is_relative_to(self.framework_dir):
                raise PermissionError("VOYEUR: Чтение разрешено только в пределах JAWL.")
            return resolved_path

        if not resolved_path.is_relative_to(self.sandbox_dir):
            raise PermissionError(
                f"CAGE: Доступ разрешен строго внутри sandbox/. Путь '{resolved_path}' отклонен."
            )

        return resolved_path

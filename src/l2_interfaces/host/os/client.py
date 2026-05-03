"""
Центральный клиент взаимодействия агента с операционной системой хоста.

Выступает в роли Гейткипера (Gatekeeper): перехватывает все обращения к файловой системе,
резолвит пути и жестко блокирует атаки типа Path Traversal (выход за пределы директории)
на основе выданного Access Level. Управляет рабочим пространством (Workspace) агента.
"""

import sys
import json
from enum import IntEnum
from pathlib import Path
import shutil
from typing import Union, Dict, Any

from src.utils.logger import system_logger
from src.utils.settings import HostOSConfig
from src.l2_interfaces.host.os.state import HostOSState

from src.l2_interfaces.host.os.deploy_manager import HostOSDeployManager


class HostOSAccessLevel(IntEnum):
    """
    Уровни доступа агента к хост-системе (RBAC).
    """

    SANDBOX = 0  # Read/Write только внутри sandbox/
    OBSERVER = 1  # Read фреймворка, Write в sandbox/
    OPERATOR = 2  # Read/Write только внутри директории фреймворка JAWL
    ROOT = 3  # Полный Read/Write по всей системе


class HostOSClient:
    """Менеджер операционной системы и Гейткипер путей."""

    def __init__(
        self,
        base_dir: Union[Path, str],
        config: HostOSConfig,
        state: HostOSState,
        timezone: int,
    ) -> None:
        """
        Инициализирует клиент ОС и подготавливает системные папки.

        Args:
            base_dir: Путь к корню фреймворка.
            config: Конфигурация интерфейса ОС.
            state: L0 стейт (приборная панель агента).
            timezone: Смещение часового пояса.
        """
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
        self.system_dir = self.sandbox_dir / "_system"
        self.download_dir = self.system_dir / "download"
        self.events_dir = self.system_dir / ".jawl_events"

        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.system_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)

        system_logger.info(
            f"[Host OS] Клиент инициализирован (ОС: {self.os_platform}, Access Level: {self.access_level})."
        )
        self.state.is_online = True

        # Файл для реестра описаний файлов
        self.metadata_file = (
            self.framework_dir
            / "src"
            / "utils"
            / "local"
            / "data"
            / "interfaces"
            / "host"
            / "os"
            / "file_meta.json"
        )
        self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.metadata_file.exists():
            self.metadata_file.write_text("{}", encoding="utf-8")

        # Файл-реестр запущенных демонов
        self.daemons_file = (
            self.framework_dir
            / "src"
            / "utils"
            / "local"
            / "data"
            / "interfaces"
            / "host"
            / "os"
            / "daemons.json"
        )
        self.daemons_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.daemons_file.exists():
            self.daemons_file.write_text("{}", encoding="utf-8")

        self._ensure_sandbox_api()

        # Инициализация менеджера деплоя
        self.deploy_manager = HostOSDeployManager(
            self.framework_dir, max_retries=self.config.deploy_max_retries
        )

    # =================================================================================
    # GATEKEEPER (Резолвинг путей и проверки безопасности)
    # =================================================================================

    def validate_path(self, target_path: Union[str, Path], is_write: bool = False) -> Path:
        """
        Умный маршрутизатор и гейткипер.
        Переводит относительные пути агента в абсолютные физические адреса ОС
        и жестко проверяет права доступа согласно текущим политикам безопасности.

        Args:
            target_path: Запрошенный агентом путь (например, 'sandbox/test.py' или '../main.py').
            is_write: Является ли операция деструктивной (запись/удаление).

        Returns:
            Физический, очищенный и разрешенный абсолютный путь (Path).

        Raises:
            PermissionError: Если агент сует свой нос туда, куда ему не положено по уровню доступа.
        """

        resolved_path = self._resolve_path(target_path, is_write)
        self._check_security_policies(resolved_path, is_write)
        return resolved_path

    def _resolve_path(self, target_path: Union[str, Path], is_write: bool) -> Path:
        """
        Вычисляет абсолютный адрес файла на диске.
        Все относительные пути строго резолвятся от корня фреймворка (JAWL/).
        Никакого DWIM (угадывания) - что агент передал, туда и идем.
        """

        path_str = str(target_path).replace("\\", "/").strip()
        path_obj = Path(path_str)

        if path_obj.is_absolute():
            return path_obj.resolve()

        fw_name = self.framework_dir.name

        # Поддержка, если агент зачем-то указал имя корня (например, "JAWL/sandbox/test.py")
        if path_str.startswith(f"{fw_name}/"):
            path_str = path_str[len(fw_name) + 1 :]
        elif path_str == fw_name:
            return self.framework_dir.resolve()

        # Просто приклеиваем переданный путь к корню фреймворка
        return (self.framework_dir / path_str).resolve()

    def _check_security_policies(self, resolved_path: Path, is_write: bool) -> None:
        """Жестко валидирует права доступа. Бросает PermissionError при нарушениях."""

        # 1. Защита ключей API
        if not self.config.env_access and ".env" in resolved_path.name.lower():
            raise PermissionError(
                f"SYSTEM DENIED: Доступ к файлам конфигурации ({resolved_path.name}) запрещен."
            )

        # 2. Защита системной директории песочницы (от случайного удаления скриптов демонов)
        if is_write and resolved_path.is_relative_to(self.system_dir):
            if not resolved_path.is_relative_to(self.download_dir):
                raise PermissionError(
                    "SYSTEM DENIED: Папка 'sandbox/_system/' является системной и защищенной. "
                    "Её нельзя изменять, удалять или создавать в ней скрипты/файлы "
                    "(исключение: чтение и запись разрешены в sandbox/_system/download/)."
                )

        # 3. Защита конфигурации (Config Override)
        config_dir = self.framework_dir / "config"
        if is_write and resolved_path.is_relative_to(config_dir):
            if self.access_level < HostOSAccessLevel.ROOT:
                raise PermissionError(
                    "SYSTEM DENIED: Изменение файлов в папке 'config/' "
                    "запрещено для вашего уровня доступа. Требуется ROOT (3). "
                    "Для безопасного изменения конфигурации рекомендуется использовать навыки Meta-интерфейса."
                )

        # 4. Применение Role-Based Access Control (RBAC)
        if self.access_level == HostOSAccessLevel.ROOT:
            pass
        elif self.access_level == HostOSAccessLevel.OPERATOR:
            if not resolved_path.is_relative_to(self.framework_dir):
                raise PermissionError(
                    "OPERATOR: Доступ (чтение и запись) разрешен строго только в директории JAWL."
                )
        elif self.access_level == HostOSAccessLevel.OBSERVER:
            if is_write and not resolved_path.is_relative_to(self.sandbox_dir):
                raise PermissionError("OBSERVER: Запись разрешена строго в папке sandbox/.")
            if not is_write and not resolved_path.is_relative_to(self.framework_dir):
                raise PermissionError("OBSERVER: Чтение разрешено только в пределах JAWL.")
        elif not resolved_path.is_relative_to(self.sandbox_dir):
            raise PermissionError(
                f"SANDBOX: Доступ разрешен строго внутри sandbox/. Путь '{resolved_path}' отклонен."
            )

        # 5. Логика Deploy Sessions (бекапы исходного кода фреймворка)
        is_framework_code = (
            resolved_path.is_relative_to(self.framework_dir)
            and not resolved_path.is_relative_to(self.sandbox_dir)
            and not resolved_path.is_relative_to(self.framework_dir / "logs")
            and not resolved_path.is_relative_to(
                self.framework_dir / "src" / "utils" / "local" / "data"
            )
        )

        if is_write and is_framework_code and self.config.require_deploy_sessions:
            if not self.deploy_manager.is_active:
                raise PermissionError(
                    "SYSTEM DENIED: Для изменения исходного кода фреймворка необходимо сначала открыть деплой-сессию (навык start_deploy_session)."
                )
            # Если пишем в код во время сессии - делаем бекап
            self.deploy_manager.backup_file(resolved_path)

    # =================================================================================
    # УТИЛИТЫ И КОНТЕКСТ
    # =================================================================================

    def get_file_metadata(self) -> Dict[str, str]:
        """Читает реестр описаний файлов (Метаданные, оставленные агентом)."""
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

    def remove_file_metadata(self, rel_path: str) -> None:
        """Удаляет описание файла из реестра, если оно существует."""
        data = self.get_file_metadata()
        if rel_path in data:
            del data[rel_path]
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    def _ensure_sandbox_api(self) -> None:
        """Копирует библиотеку `framework_api` из темплейтов в песочницу для скриптов агента."""
        api_path = self.system_dir / "framework_api.py"
        template_path = self.framework_dir / "src" / "utils" / "templates" / "framework_api.py"

        if template_path.exists():
            shutil.copy2(template_path, api_path)
        else:
            system_logger.warning("[Host OS] Шаблон framework_api.py не найден.")

    def get_daemons_registry(self) -> Dict[str, Any]:
        """Возвращает информацию о запущенных фоновых скриптах."""
        try:
            with open(self.daemons_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def set_daemons_registry(self, data: Dict[str, Any]) -> None:
        """Обновляет информацию о фоновых скриптах."""
        with open(self.daemons_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок телеметрии, файловой системы и воркспейса.
        """
        if not self.state.is_online:
            return "### HOST OS [OFF]\nИнтерфейс отключен."

        framework_block = ""
        if self.access_level >= HostOSAccessLevel.OBSERVER and self.state.framework_files:
            framework_block = f"{self.state.framework_files}"
        else:
            framework_block = "Нет доступа к полной директории фреймворка."

        access_levels_desc = (
            "Существующие уровни доступа: \n"
            "- 0/SANDBOX: Read/Write только внутри папки sandbox/.\n"
            "- 1/OBSERVER: Read для всего кода фреймворка, Write только в sandbox/.\n"
            "- 2/OPERATOR: Read/Write только внутри директории фреймворка JAWL.\n"
            "- 3/ROOT: Полный доступ. Read/Write всей системы и управление процессами."
        )

        if self.deploy_manager.is_active:
            access_levels_desc += f"\n\n[DEPLOY SESSION ACTIVE] Активирована возможность менять код фреймворка. Попыток коммита осталось: {self.deploy_manager.retries_left}."

        # ===============================================
        # Сборка открытых файлов (те файлы, которые агент открыл в контексте)

        workspace_block = ""
        if self.state.opened_workspace_files:
            max_tabs = self.config.workspace_max_opened_files
            current_tabs = len(self.state.opened_workspace_files)

            ws_lines = [f"Открытые файлы ({current_tabs}/{max_tabs}):"]

            for rel_path in list(self.state.opened_workspace_files):
                try:
                    full_path = self.validate_path(rel_path, is_write=False)
                    if full_path.exists() and full_path.is_file():

                        try:
                            display_path = full_path.relative_to(self.framework_dir).as_posix()
                        except ValueError:
                            display_path = full_path.as_posix()

                        content = full_path.read_text(encoding="utf-8", errors="replace")

                        limit = self.config.workspace_max_file_chars
                        if len(content) > limit:
                            content = (
                                content[:limit]
                                + f"\n...[Файл слишком большой, обрезан (больше {limit} символов). Для полного содержания - использовать соответствующий навык]"
                            )

                        ext = full_path.suffix.lower().strip(".")
                        lang = (
                            ext
                            if ext in ["py", "json", "yaml", "yml", "md", "html", "js", "css"]
                            else ""
                        )
                        if ext == "py":
                            lang = "python"

                        ws_lines.append(
                            f"\n\n#### Вкладка: {display_path} \n```{lang}\n{content}\n```"
                        )
                    else:
                        self.state.opened_workspace_files.discard(rel_path)
                except Exception:
                    pass
            workspace_block = "\n" + "\n".join(ws_lines) + "\n"
        else:
             workspace_block = "Нет открытых вкладок."

        # ===============================================
        # Сборка истории изменений

        recent_changes_block = ""
        if self.state.recent_file_changes:
            rc_lines = [""]
            rc_lines.extend(self.state.recent_file_changes)
            recent_changes_block = "" + "\n\n".join(rc_lines) + "\n"
        else: 
            recent_changes_block = "Нет последних изменений."

        # ===============================================
        # Абсолютные пути, если активен уровень доступа ROOT

        absolute_paths_block = ""
        if self.access_level == HostOSAccessLevel.ROOT:
            home_dir = Path.home().resolve().as_posix()
            fw_dir = self.framework_dir.resolve().as_posix()
            absolute_paths_block = (
                f"\n[Активен уровен доступа ROOT]\n"
                f"* Абсолютный путь фреймворка: {fw_dir}\n"
                f"* Домашняя директория: {home_dir}\n"
            )

        # ===============================================
        # Финальная сборка

        return f"""
### HOST OS [ON]

* Current Datetime: {self.state.datetime}

* OS: {self.state.os_info}
* Uptime: {self.state.uptime}

* Network: \n{getattr(self.state, 'network', 'Неизвестно')}

* Telemetry: {self.state.telemetry}

* Polling interval: {self.state.polling_interval}

* Active Daemons:
{self.state.active_daemons}

* Current Access Level: {self.access_level.value}/{self.access_level.name} (текущий уровень доступа)
{access_levels_desc}
{absolute_paths_block}

* Framework Directory:
{framework_block}

* Sandbox Directory:
{self.state.sandbox_files}

* Recent Changes in Files:
{recent_changes_block}

* Workspace:
{workspace_block}

[Напоминание] 
- Папка sandbox/_system/ является системной и не подлежит изменению.
- Внутри неё также находится файл 'framework_api.py'. 
- Этот файл позволяет взаимодействовать с пробуждениями и контекстом агента.

- Все относительные пути строго исчисляются от корневой директории фреймворка (JAWL/).
- Если необходимо создать файл в песочнице - нужно указывать это (например, `sandbox/имя_файла.py`).
""".strip()

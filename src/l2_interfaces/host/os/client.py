"""
Central client for agent interaction with the host operating system.

Acts as a Gatekeeper: intercepts all file system calls,
resolves paths, and strictly blocks Path Traversal attacks (escaping directory bounds)
based on the active Access Level. Manages the agent's Workspace.
"""

import sys
import json
from enum import IntEnum
from pathlib import Path
import shutil
from typing import Union, Dict, Any

from src.utils.logger import main_logger
from src.utils.settings import HostOSConfig
from src.l2_interfaces.host.os.state import HostOSState

from src.l2_interfaces.host.os.deploy_manager import HostOSDeployManager


class HostOSAccessLevel(IntEnum):
    """
    Agent access levels to the host system (RBAC).
    """

    SANDBOX = 0  # Read/Write strictly inside sandbox/
    OBSERVER = 1  # Read framework, Write inside sandbox/
    OPERATOR = 2  # Read/Write strictly inside the JAWL framework directory
    ROOT = 3  # Full Read/Write across the entire system


class HostOSClient:
    """Operating system manager and path Gatekeeper."""

    def __init__(
        self,
        base_dir: Union[Path, str],
        config: HostOSConfig,
        state: HostOSState,
        timezone: int,
    ) -> None:
        """
        Initializes the OS client and prepares system folders.

        Args:
            base_dir: Path to the framework root.
            config: OS interface configuration.
            state: L0 state (agent dashboard).
            timezone: Timezone offset.
        """
        self.config = config
        self.state = state
        self.timezone = timezone

        try:
            self.access_level = HostOSAccessLevel(self.config.access_level)
        except ValueError:
            main_logger.warning(
                f"[Host OS] Unknown access_level: {self.config.access_level}. Resetting to SANDBOX (0)."
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

        main_logger.info(
            f"[Host OS] Client initialized (OS: {self.os_platform}, Access Level: {self.access_level})."
        )
        self.state.is_online = True

        # File metadata registry file
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

        # Daemon registry file
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

        # Deploy manager initialization
        self.deploy_manager = HostOSDeployManager(
            self.framework_dir, max_retries=self.config.deploy_max_retries
        )

    # =================================================================================
    # GATEKEEPER (Path resolution and security checks)
    # =================================================================================

    def validate_path(self, target_path: Union[str, Path], is_write: bool = False) -> Path:
        """
        Smart router and path gatekeeper.
        Resolves relative agent paths to absolute physical OS addresses
        and strictly verifies access rights based on active security policies.

        Args:
            target_path: Path requested by the agent (e.g., 'sandbox/test.py' or '../main.py').
            is_write: Is the operation destructive (write/delete).

        Returns:
            Physical, cleaned, and resolved absolute path (Path).

        Raises:
            PermissionError: If the agent attempts to access paths forbidden by its access level.
        """

        resolved_path = self._resolve_path(target_path, is_write)
        self._check_security_policies(resolved_path, is_write)
        return resolved_path

    def _resolve_path(self, target_path: Union[str, Path], is_write: bool) -> Path:
        """
        Calculates the absolute address of a file on disk.
        All relative paths are strictly resolved from the framework root (JAWL/).
        """

        path_str = str(target_path).replace("\\", "/").strip()
        path_obj = Path(path_str)

        if path_obj.is_absolute():
            return path_obj.resolve()

        fw_name = self.framework_dir.name

        # Support for cases where the agent specified the root directory name (e.g., "JAWL/sandbox/test.py")
        if path_str.startswith(f"{fw_name}/"):
            path_str = path_str[len(fw_name) + 1 :]
        elif path_str == fw_name:
            return self.framework_dir.resolve()

        # Append the passed path directly to the framework root
        return (self.framework_dir / path_str).resolve()

    def _check_security_policies(self, resolved_path: Path, is_write: bool) -> None:
        """Strictly validates access rights. Raises PermissionError on violations."""

        # 1. API Keys protection
        if not self.config.env_access and ".env" in resolved_path.name.lower():
            raise PermissionError(
                f"SYSTEM DENIED: Access to configuration files ({resolved_path.name}) is forbidden."
            )

        # 2. Sandbox system directory protection (prevents accidental deletion of daemon scripts)
        if is_write and resolved_path.is_relative_to(self.system_dir):
            if not resolved_path.is_relative_to(self.download_dir):
                raise PermissionError(
                    "SYSTEM DENIED: Folder 'sandbox/_system/' is system-owned and protected. "
                    "Modifying, deleting, or creating files in it is forbidden "
                    "(exception: read and write are allowed in sandbox/_system/download/)."
                )

        # 3. Configuration protection (Config Override)
        config_dir = self.framework_dir / "config"
        if is_write and resolved_path.is_relative_to(config_dir):
            if self.access_level < HostOSAccessLevel.ROOT:
                raise PermissionError(
                    "SYSTEM DENIED: Modifying files in the 'config/' folder is forbidden "
                    "for your access level. ROOT (3) is required. "
                    "Meta-interface skills are recommended for safe configuration modification."
                )

        # 4. Role-Based Access Control (RBAC) enforcement
        if self.access_level == HostOSAccessLevel.ROOT:
            pass
        elif self.access_level == HostOSAccessLevel.OPERATOR:
            if not resolved_path.is_relative_to(self.framework_dir):
                raise PermissionError(
                    "OPERATOR: Access (read and write) is permitted strictly within the JAWL directory."
                )
        elif self.access_level == HostOSAccessLevel.OBSERVER:
            if is_write and not resolved_path.is_relative_to(self.sandbox_dir):
                raise PermissionError(
                    "OBSERVER: Writing is permitted strictly inside the sandbox/ folder."
                )
            if not is_write and not resolved_path.is_relative_to(self.framework_dir):
                raise PermissionError(
                    "OBSERVER: Reading is permitted strictly within JAWL limits."
                )
        elif not resolved_path.is_relative_to(self.sandbox_dir):
            raise PermissionError(
                f"SANDBOX: Access is permitted strictly inside sandbox/. Path '{resolved_path}' was denied."
            )

        # 5. Deploy Sessions logic (framework source code backups)
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
                    "SYSTEM DENIED: Modifying framework source code requires an active deploy session (start_deploy_session skill)."
                )
            # Back up file if modifying source code during active deploy session
            self.deploy_manager.backup_file(resolved_path)

    # =================================================================================
    # UTILITIES AND CONTEXT
    # =================================================================================

    def get_file_metadata(self) -> Dict[str, str]:
        """Reads the file descriptions registry (metadata left by the agent)."""
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def set_file_metadata(self, rel_path: str, description: str) -> None:
        """Saves description for a specific file."""
        data = self.get_file_metadata()
        data[rel_path] = description
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def remove_file_metadata(self, rel_path: str) -> None:
        """Deletes file description from the registry, if it exists."""
        data = self.get_file_metadata()
        if rel_path in data:
            del data[rel_path]
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    def _ensure_sandbox_api(self) -> None:
        """Copies `framework_api` from templates to the sandbox for agent scripts."""
        api_path = self.system_dir / "framework_api.py"
        template_path = self.framework_dir / "src" / "utils" / "templates" / "framework_api.py"

        if template_path.exists():
            shutil.copy2(template_path, api_path)
        else:
            main_logger.warning("[Host OS] Template framework_api.py not found.")

    def get_daemons_registry(self) -> Dict[str, Any]:
        """Returns info about running background scripts."""
        try:
            with open(self.daemons_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def set_daemons_registry(self, data: Dict[str, Any]) -> None:
        """Updates info about background scripts."""
        with open(self.daemons_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Context provider for ContextRegistry.
        Returns a formatted block of telemetry, file system, and workspace.
        """

        desc = "Description: Host operating system access (files, processes, shell, network)."

        if not self.state.is_online:
            return f"### HOST OS [OFF]\n{desc}\nThe interface is disabled."

        framework_block = ""
        if self.access_level >= HostOSAccessLevel.OBSERVER and self.state.framework_files:
            framework_block = f"{self.state.framework_files}"
        else:
            framework_block = "No access to the full framework directory."

        access_levels_desc = (
            "Existing access levels: \n"
            "- 0/SANDBOX: Read/Write strictly inside sandbox/.\n"
            "- 1/OBSERVER: Read framework, Write inside sandbox/.\n"
            "- 2/OPERATOR: Read/Write strictly inside the JAWL framework directory.\n"
            "- 3/ROOT: Full Read/Write across the entire system."
        )

        if self.deploy_manager.is_active:
            access_levels_desc += f"\n\n[DEPLOY SESSION ACTIVE] The ability to change framework code has been enabled. Remaining commit attempts: {self.deploy_manager.retries_left}."

        # ===============================================
        # Assemble open files (files the agent opened in the context)

        workspace_block = ""
        if self.state.opened_workspace_files:
            max_tabs = self.config.workspace_max_opened_files
            current_tabs = len(self.state.opened_workspace_files)

            ws_lines = [f"Open files ({current_tabs}/{max_tabs}):"]

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
                                + f"\n...[The file is too large and has been truncated (more than {limit} characters). For full content - use the appropriate skill]"
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
                            f"\n\n#### Tab: {display_path} \n```{lang}\n{content}\n```"
                        )
                    else:
                        self.state.opened_workspace_files.discard(rel_path)
                except Exception:
                    pass
            workspace_block = "\n" + "\n".join(ws_lines) + "\n"
        else:
            workspace_block = "No open tabs."

        # ===============================================
        # Assemble changes history

        recent_changes_block = ""
        if self.state.recent_file_changes:
            rc_lines = [""]
            rc_lines.extend(self.state.recent_file_changes)
            recent_changes_block = "" + "\n\n".join(rc_lines) + "\n"
        else:
            recent_changes_block = "No recent changes."

        # ===============================================
        # Absolute paths, if ROOT access level is active

        absolute_paths_block = ""
        if self.access_level == HostOSAccessLevel.ROOT:
            home_dir = Path.home().resolve().as_posix()
            fw_dir = self.framework_dir.resolve().as_posix()
            absolute_paths_block = (
                f"\n[ROOT access level is active]\n"
                f"* Absolute path of the framework: {fw_dir}\n"
                f"* Home directory: {home_dir}\n"
            )

        # ===============================================
        # Tracked directories

        tracked_dirs_block = ""
        if self.state.tracked_dirs_trees:
            tracked_dirs_block = f"\n{self.state.tracked_dirs_trees}\n"
        else:
            tracked_dirs_block = "There are no watched directories."

        # ===============================================
        # Final assembly

        return f"""
### HOST OS [ON]
{desc}

* Current Datetime: {self.state.datetime}

* OS: {self.state.os_info}
* Uptime: {self.state.uptime}

* Network: \n{getattr(self.state, 'network', 'Unknown')}

* Telemetry: 
{self.state.telemetry}

* Polling interval: {self.state.polling_interval}

* Active Daemons:
{self.state.active_daemons}

* Current Access Level: {self.access_level.value}/{self.access_level.name}
{access_levels_desc}
{absolute_paths_block}

* Framework Directory:
{framework_block}

* Sandbox Directory:
{self.state.sandbox_files}

* Tracked Directories:
{tracked_dirs_block}

* Recent Changes in Files:
{recent_changes_block}

* Workspace:
{workspace_block}

[Reminder]
- sandbox/_system/ is a system folder and immutable.
- It contains 'framework_api.py'.
- This file enables interaction with system awakenings and context.
- All relative paths are strictly calculated from the framework root (JAWL/).
- To create a file in the sandbox, specify the path (e.g., sandbox/test.py).
""".strip()

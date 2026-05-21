"""
Manages deploy sessions, backups (Copy-on-Write), and test verifications.
"""

import sys
import os
import shutil
import asyncio
from pathlib import Path
from typing import Tuple

from src import __version__
from src.utils.logger import main_logger


class HostOSDeployManager:
    """
    Manages deploy sessions, backups (Copy-on-Write), and test verifications.
    """

    def __init__(self, framework_dir: Path, max_retries: int = 5) -> None:
        self.framework_dir = framework_dir
        self.backup_dir = framework_dir / "src" / "utils" / "local" / "data" / "deploy_backup"
        self.active_flag = self.backup_dir / ".deploy_active"
        self.manifest_file = self.backup_dir / ".newfiles_manifest"

        self.is_active = False
        self.max_retries = max_retries
        self.retries_left = self.max_retries

        if self.active_flag.exists():
            self.is_active = True

    def start_session(self) -> Tuple[bool, str]:
        if self.is_active:
            return False, "Deploy session is already active."

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.active_flag.touch()
        self.is_active = True
        self.retries_left = self.max_retries

        if not self.manifest_file.exists():
            self.manifest_file.touch()

        main_logger.info(
            f"[Deploy] Deploy session successfully initialized (JAWL v{__version__})."
        )
        return (
            True,
            f"Deploy session started. You have {self.max_retries} attempts to pass tests upon commit.",
        )

    def backup_file(self, filepath: Path) -> None:
        if not self.is_active:
            return

        rel_path = filepath.relative_to(self.framework_dir)
        backup_path = self.backup_dir / rel_path

        if backup_path.exists():
            return

        if filepath.exists():
            if filepath.is_dir():
                for child in filepath.rglob("*"):
                    if child.is_file():
                        self.backup_file(child)
                return

            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, backup_path)
            main_logger.debug(f"[Deploy] File backed up: {rel_path}")
        else:
            with open(self.manifest_file, "a", encoding="utf-8") as f:
                f.write(f"{rel_path}\n")
            main_logger.debug(f"[Deploy] New file added to manifest: {rel_path}")

    async def commit_session(
        self,
        test_path: str = "tests/unit/",
        force: bool = False,
    ) -> Tuple[bool, str]:
        """
        Closes the deploy session and commits changes.
        Automatically launches the syntax analyzer (compileall) and tests (pytest).
        If tests fail, consumes one attempt. If attempts are exhausted, calls rollback_session().

        Args:
            test_path: Which tests to run. Defaults to all unit tests.
            force: If True, ignores pytest failure and commits code (not recommended).
        """

        if not self.is_active:
            return False, "No active deploy session."

        main_logger.info(
            f"[Deploy] Starting changes validation (force={force}, target={test_path})."
        )

        # 1. Syntax check (MANDATORY)
        proc_syntax = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "src/",
            cwd=str(self.framework_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_syntax = await asyncio.wait_for(proc_syntax.communicate(), timeout=30)

        if proc_syntax.returncode != 0:
            return self._handle_failure(
                f"Syntax Error (SyntaxError):\n{stderr_syntax.decode('utf-8', errors='replace')}"
            )

        # 2. Running all Unit tests (Pytest)
        test_args = test_path.split()

        proc_tests = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--disable-warnings",
            *test_args,
            cwd=str(self.framework_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_test, stderr_test = await asyncio.wait_for(
            proc_tests.communicate(), timeout=120
        )

        if proc_tests.returncode != 0:
            out_str = stdout_test.decode("utf-8", errors="replace")
            err_msg = out_str[-10000:] if len(out_str) > 10000 else out_str

            if force:
                main_logger.warning(
                    "[Deploy] Tests failed, but FORCE commit applied. Saving changes."
                )
                self._cleanup()
                return (
                    True,
                    f"Warning: Tests failed, but commit is forcefully saved (force=True). Log:\n{err_msg}\n\nDeploy session closed.",
                )
            else:
                return self._handle_failure(f"Tests failed:\n{err_msg}")

        self._cleanup()
        main_logger.info("[Deploy] Tests passed. Changes successfully committed.")
        return (
            True,
            "Tests passed. Code is committed, deploy session closed. It is recommended to initiate a system reboot to apply changes.",
        )

    def _handle_failure(self, error_report: str) -> Tuple[bool, str]:
        self.retries_left -= 1
        if self.retries_left > 0:
            main_logger.warning(
                f"[Deploy] Tests failed. Remaining attempts: {self.retries_left}."
            )
            msg = f"Deploy error. \n{error_report} \n\nRemaining attempts to fix the error: {self.retries_left}."
            return False, msg
        else:
            main_logger.error("[Deploy] Attempts exhausted. Rolling back changes.")
            self.rollback_session()
            msg = f"Deploy error. \n{error_report} \n\nAttempts exhausted. All changes in the framework code have been automatically reverted. Deploy session closed."
            return False, msg

    def rollback_session(self) -> Tuple[bool, str]:
        if not self.is_active:
            return False, "No active deploy session."

        for root, dirs, files in os.walk(self.backup_dir):
            if "__pycache__" in root:
                continue
            for file in files:
                if file in (".deploy_active", ".newfiles_manifest") or file.endswith(".pyc"):
                    continue
                backup_path = Path(root) / file
                rel_path = backup_path.relative_to(self.backup_dir)
                target_path = self.framework_dir / rel_path

                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, target_path)

        if self.manifest_file.exists():
            with open(self.manifest_file, "r", encoding="utf-8") as f:
                new_files = f.read().splitlines()
            for nf in new_files:
                if nf:
                    target = self._resolve_manifest_target(nf)
                    if target is None:
                        main_logger.warning(
                            f"[Deploy] Skipped unsafe manifest entry during rollback: {nf}"
                        )
                        continue
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target, ignore_errors=True)
                        else:
                            target.unlink(missing_ok=True)

        self._cleanup()
        main_logger.info("[Deploy] Changes successfully rolled back (Rollback).")
        return (
            True,
            "Rollback completed successfully. System files restored to the state at the beginning of the session.",
        )

    def _resolve_manifest_target(self, manifest_entry: str) -> Path | None:
        """
        Safely resolves path from .newfiles_manifest.

        The manifest contains relative paths of new files inside framework_dir.
        If an absolute path or traversal via '..' gets in there, the old code could
        delete an arbitrary file on rollback. Therefore, any entries outside
        framework_dir are rejected.
        """

        entry = manifest_entry.strip()
        if not entry:
            return None

        entry_path = Path(entry)
        if entry_path.is_absolute():
            return None

        target = (self.framework_dir / entry_path).resolve()
        framework_root = self.framework_dir.resolve()
        if not target.is_relative_to(framework_root):
            return None

        return target

    def _cleanup(self) -> None:
        shutil.rmtree(self.backup_dir, ignore_errors=True)
        self.is_active = False

"""
Shared Sandbox Guard.

IMPORTANT: this is NOT real isolation. Pure-Python in-process guard is intended
for protection against trivial/casual escapes. Any motivated attacker
can bypass it (on the level of ctypes/Cython/C extension/mmap/direct syscall).

For serious isolation use:
  - a separate process in a namespace + seccomp (Linux)
  - Docker / Podman container
  - WASM (Pyodide)
  - a full VM sandbox

This module unifies the common logic for `sandbox_runner.py` and `rpc_wrapper.py`
so that protection does not diverge between the two code execution paths in the sandbox.
"""

from __future__ import annotations

import builtins
import ctypes
import importlib
import io
import os
import subprocess
import sys
import _io
from pathlib import Path
from typing import Any, Callable

# ----------------------------------------------------------------------
# Secret scrubbing from os.environ
# ----------------------------------------------------------------------
_ALLOWED_ENV_PREFIXES: tuple[str, ...] = ("JAWL_",)
_ALLOWED_ENV_NAMES: frozenset[str] = frozenset(
    {
        "PATH",
        "PWD",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SHELL",
        "TERM",
        "TZ",
        "USER",
        "LOGNAME",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONIOENCODING",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "OS",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
    }
)
# Substrings indicating a secret. Wide filter — better to remove too much than to miss.
_SECRET_HINTS: tuple[str, ...] = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASS",
    "PWD",
    "CRED",
    "API",
    "AUTH",
    "SESSION",
    "COOKIE",
    "BEARER",
    "PRIVATE",
    "CERT",
    "SIGNATURE",
    "OAUTH",
    "DSN",
    "CONNECTION",
    "URI",
    "URL",
    "WEBHOOK",
    "ACCESS",
    "LICENSE",
)


def scrub_environ() -> None:
    """Removes all variables that look like a secret from os.environ."""

    for name in list(os.environ.keys()):
        up = name.upper()
        if name in _ALLOWED_ENV_NAMES:
            continue
        if any(up.startswith(p) for p in _ALLOWED_ENV_PREFIXES):
            continue
        if any(h in up for h in _SECRET_HINTS):
            del os.environ[name]


# ----------------------------------------------------------------------
# Path resolving and checks for escaping the sandbox
# ----------------------------------------------------------------------
def _is_system_python_path(p: Path) -> bool:
    """Python stdlib / site-packages paths are allowed for reading."""

    s = str(p).lower()
    if "site-packages" in s:
        return True
    if "/lib/python" in s or "\\lib\\python" in s:
        return True
    if "/lib-dynload" in s or "\\lib-dynload" in s:
        return True
    # Python distribution prefix paths (for venv/conda/embedded).
    for prefix in (sys.base_prefix, sys.prefix, sys.exec_prefix):
        if prefix and s.startswith(prefix.lower()):
            return True
    return False


class PathChecker:
    """Checks that the file path remains in sandbox_dir."""

    def __init__(self, framework_dir: Path, sandbox_dir: Path) -> None:
        self.framework_dir = framework_dir.resolve()
        self.sandbox_dir = sandbox_dir.resolve()

    def check(self, file: Any) -> None:
        """Throws PermissionError if the path is outside the sandbox.

        Integer fd is not checked — it is assumed that the descriptor
        has already passed through the patched os.open.
        """

        if isinstance(file, int):
            return

        try:
            if isinstance(file, bytes):
                file = file.decode(errors="ignore")
            p = Path(file).resolve()
        except Exception:  # noqa: BLE001
            # If the path does not resolve, real open will fail itself with FileNotFoundError.
            return

        if p.is_relative_to(self.sandbox_dir):
            return

        if _is_system_python_path(p):
            return

        raise PermissionError(
            f"[Sandbox Guard] Access Denied: Path Traversal attempt blocked. Access to '{file}' is forbidden."
        )


# ----------------------------------------------------------------------
# API Blocking
# ----------------------------------------------------------------------
def _blocked_func(*args: Any, **kwargs: Any) -> None:  # noqa: D401, ARG001
    """Universal blocker — simply throws PermissionError."""

    raise PermissionError(
        "[Sandbox Guard] Access Denied: Usage of shell/subprocess is blocked for security reasons."
    )


def _make_guarded_open(
    orig_open: Callable[..., Any], checker: PathChecker
) -> Callable[..., Any]:
    def _safe_open(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
        checker.check(file)
        return orig_open(file, mode, *args, **kwargs)

    return _safe_open


def _install_file_guards(checker: PathChecker) -> None:
    """Patches all known high- and low-level I/O points."""

    # 1. builtins.open + io.open
    builtins.open = _make_guarded_open(builtins.open, checker)
    io.open = _make_guarded_open(io.open, checker)

    # 2. os.open (low-level)
    orig_os_open = os.open

    def _safe_os_open(path, flags, mode=0o777, *, dir_fd=None):  # type: ignore[no-untyped-def]
        checker.check(path)
        return orig_os_open(path, flags, mode, dir_fd=dir_fd)

    os.open = _safe_os_open  # type: ignore[assignment]

    # 3. _io.FileIO (bypass via CPython internal module)
    orig_FileIO = _io.FileIO

    class _SafeFileIO(orig_FileIO):  # type: ignore[misc,valid-type]
        def __init__(self, file, mode="r", closefd=True, opener=None):  # type: ignore[no-untyped-def]
            checker.check(file)
            super().__init__(file, mode, closefd, opener)

    _io.FileIO = _SafeFileIO  # type: ignore[assignment]

    # 4. pathlib interception
    # In Python 3.10 Path.open() invokes ``self._accessor.open(...)``, where
    # ``_accessor.open`` binds to the original ``os.open`` during
    # module import - before our patch. In Python 3.11+ this layer
    # is removed and ``Path.open`` calls ``io.open`` directly, but for
    # backward compatibility we reassign Path.open entirely.
    import pathlib

    _orig_path_open = pathlib.Path.open

    def _safe_path_open(
        self, mode="r", buffering=-1, encoding=None, errors=None, newline=None
    ):  # type: ignore[no-untyped-def]
        checker.check(str(self))
        # Delegate io.open explicitly to go through our patch.
        return io.open(str(self), mode, buffering, encoding, errors, newline)

    pathlib.Path.open = _safe_path_open  # type: ignore[assignment,method-assign]


def _install_process_guards() -> None:
    """Blocks subprocess / shell / fork / exec / posix_spawn."""

    # subprocess.*
    for name in (
        "Popen",
        "run",
        "call",
        "check_call",
        "check_output",
        "getoutput",
        "getstatusoutput",
    ):
        if hasattr(subprocess, name):
            setattr(subprocess, name, _blocked_func)

    # os-level shell/process
    os.system = _blocked_func  # type: ignore[assignment]
    if hasattr(os, "popen"):
        os.popen = _blocked_func  # type: ignore[assignment]

    for name in (
        "fork",
        "forkpty",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "posix_spawn",
        "posix_spawnp",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
    ):
        if hasattr(os, name):
            setattr(os, name, _blocked_func)

    # os.kill — forbid signals to parent/group (agent suicide).
    orig_os_kill = os.kill

    def _safe_os_kill(pid, sig):  # type: ignore[no-untyped-def]
        if pid <= 0 or pid == os.getppid():
            raise PermissionError(
                "[Sandbox Guard] Access Denied: sending signals to parent/group is blocked."
            )
        return orig_os_kill(pid, sig)

    os.kill = _safe_os_kill  # type: ignore[assignment]


def _install_ctypes_guard() -> None:
    """Blocks ctypes loader API (direct syscall / native-library escape)."""

    class _BlockedLibraryLoader:
        def __getattr__(self, name):  # type: ignore[no-untyped-def]
            raise PermissionError(
                "[Sandbox Guard] Access Denied: ctypes dynamic library loading is blocked."
            )

        def LoadLibrary(self, name):  # type: ignore[no-untyped-def]
            raise PermissionError(
                "[Sandbox Guard] Access Denied: ctypes dynamic library loading is blocked."
            )

    for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
        if hasattr(ctypes, name):
            setattr(ctypes, name, _blocked_func)

    for name in ("cdll", "pydll", "windll", "oledll", "pythonapi"):
        if hasattr(ctypes, name):
            setattr(ctypes, name, _BlockedLibraryLoader())

    if hasattr(ctypes, "_dlopen"):
        ctypes._dlopen = _blocked_func  # type: ignore[attr-defined]


def _install_reload_guard() -> None:
    """Does not allow importlib.reload to reload protected modules."""

    orig_reload = importlib.reload
    protected = {"os", "subprocess", "io", "_io", "mmap", "ctypes", "builtins"}

    def _safe_reload(module):  # type: ignore[no-untyped-def]
        name = getattr(module, "__name__", None)
        if name in protected:
            raise PermissionError(
                f"[Sandbox Guard] Access Denied: reloading '{name}' is blocked."
            )
        return orig_reload(module)

    importlib.reload = _safe_reload  # type: ignore[assignment]


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def install(framework_dir: Path, sandbox_dir: Path) -> None:
    """Enables all protections. Must be called BEFORE exec of user code."""

    # Scrub env first — in case user code forks and inherits variables.
    scrub_environ()

    checker = PathChecker(framework_dir, sandbox_dir)
    _install_file_guards(checker)
    _install_process_guards()
    _install_ctypes_guard()
    _install_reload_guard()


__all__ = ["install", "PathChecker", "scrub_environ"]

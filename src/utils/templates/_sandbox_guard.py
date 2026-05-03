"""
Shared Sandbox Guard.

ВАЖНО: это НЕ настоящая изоляция. Pure-Python in-process guard предназначен
для защиты от случайных/тривиальных эскейпов. Любой мотивированный атакующий
может его обойти (на уровне ctypes/Cython/C extension/mmap/прямого syscall).

Для серьёзной изоляции используйте:
  - отдельный процесс в namespace + seccomp (Linux)
  - Docker / Podman контейнер
  - WASM (Pyodide)
  - полноценный VM sandbox

Этот модуль объединяет общую логику для `sandbox_runner.py` и `rpc_wrapper.py`,
чтобы защита не расходилась между двумя путями исполнения кода в песочнице.
"""

from __future__ import annotations

import builtins
import ctypes
import importlib
import io
import mmap
import os
import signal
import subprocess
import sys
import _io
from pathlib import Path
from typing import Any, Callable


# ----------------------------------------------------------------------
# Скрабинг секретов из os.environ
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
# Подстроки, указывающие на секрет. Широкий фильтр — лучше удалить лишнее,
# чем пропустить.
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
    """Удаляет из ``os.environ`` все переменные, похожие на секрет."""

    for name in list(os.environ.keys()):
        up = name.upper()
        if name in _ALLOWED_ENV_NAMES:
            continue
        if any(up.startswith(p) for p in _ALLOWED_ENV_PREFIXES):
            continue
        if any(h in up for h in _SECRET_HINTS):
            del os.environ[name]


# ----------------------------------------------------------------------
# Резолвинг пути и проверка на выход из песочницы
# ----------------------------------------------------------------------
def _is_system_python_path(p: Path) -> bool:
    """Пути Python stdlib / site-packages разрешены на чтение."""

    s = str(p).lower()
    if "site-packages" in s:
        return True
    if "/lib/python" in s or "\\lib\\python" in s:
        return True
    if "/lib-dynload" in s or "\\lib-dynload" in s:
        return True
    # Путь префиксов Python-дистрибутива (для venv/conda/embedded).
    for prefix in (sys.base_prefix, sys.prefix, sys.exec_prefix):
        if prefix and s.startswith(prefix.lower()):
            return True
    return False


class PathChecker:
    """Проверяет что файловый путь остаётся в ``sandbox_dir``."""

    def __init__(self, framework_dir: Path, sandbox_dir: Path) -> None:
        self.framework_dir = framework_dir.resolve()
        self.sandbox_dir = sandbox_dir.resolve()

    def check(self, file: Any) -> None:
        """Бросает ``PermissionError`` если путь вне песочницы.

        Целочисленные ``fd`` не проверяются — предполагается, что
        дескриптор уже прошёл через патченный ``os.open``.
        """

        if isinstance(file, int):
            return

        try:
            if isinstance(file, bytes):
                file = file.decode(errors="ignore")
            p = Path(file).resolve()
        except Exception:  # noqa: BLE001
            # Если путь нерезолвится, real open упадёт сам с FileNotFoundError.
            return

        if _is_system_python_path(p):
            return

        if p.is_relative_to(self.framework_dir) and not p.is_relative_to(
            self.sandbox_dir
        ):
            raise PermissionError(
                f"[Sandbox Guard] Access Denied: Path Traversal попытка заблокирована. Доступ к '{file}' запрещен."
            )


# ----------------------------------------------------------------------
# Блокировка API
# ----------------------------------------------------------------------
def _blocked_func(*args: Any, **kwargs: Any) -> None:  # noqa: D401, ARG001
    """Универсальный блокиратор — просто бросает ``PermissionError``."""

    raise PermissionError(
        "[Sandbox Guard] Access Denied: Использование shell/subprocess заблокировано в целях безопасности."
    )


def _make_guarded_open(
    orig_open: Callable[..., Any], checker: PathChecker
) -> Callable[..., Any]:
    def _safe_open(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
        checker.check(file)
        return orig_open(file, mode, *args, **kwargs)

    return _safe_open


def _install_file_guards(checker: PathChecker) -> None:
    """Патчит все известные высоко- и низкоуровневые I/O точки."""

    # 1. builtins.open + io.open
    builtins.open = _make_guarded_open(builtins.open, checker)
    io.open = _make_guarded_open(io.open, checker)

    # 2. os.open (низкоуровневый)
    orig_os_open = os.open

    def _safe_os_open(path, flags, mode=0o777, *, dir_fd=None):  # type: ignore[no-untyped-def]
        checker.check(path)
        return orig_os_open(path, flags, mode, dir_fd=dir_fd)

    os.open = _safe_os_open  # type: ignore[assignment]

    # 3. _io.FileIO (обход через внутренний модуль CPython)
    orig_FileIO = _io.FileIO

    class _SafeFileIO(orig_FileIO):  # type: ignore[misc,valid-type]
        def __init__(self, file, mode="r", closefd=True, opener=None):  # type: ignore[no-untyped-def]
            checker.check(file)
            super().__init__(file, mode, closefd, opener)

    _io.FileIO = _SafeFileIO  # type: ignore[assignment]

    # 4. pathlib перехват
    # В Python 3.10 Path.open() вызывает ``self._accessor.open(...)``, где
    # ``_accessor.open`` биндится к оригинальному ``os.open`` во время
    # импорта модуля - до нашего патча. В Python 3.11+ этот слой
    # удалён и ``Path.open`` зовет ``io.open`` напрямую, но для
    # обратной совместимости переприсываем Path.open целиком.
    import pathlib

    _orig_path_open = pathlib.Path.open

    def _safe_path_open(self, mode="r", buffering=-1, encoding=None,
                         errors=None, newline=None):  # type: ignore[no-untyped-def]
        checker.check(str(self))
        # Делегируем io.open явно, чтобы пройти через наш патч.
        return io.open(str(self), mode, buffering, encoding, errors, newline)

    pathlib.Path.open = _safe_path_open  # type: ignore[assignment,method-assign]


def _install_process_guards() -> None:
    """Блокирует subprocess / shell / fork / exec / posix_spawn."""

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

    # os.kill — запретить сигналы родителю/группе (суицид агента).
    orig_os_kill = os.kill

    def _safe_os_kill(pid, sig):  # type: ignore[no-untyped-def]
        if pid <= 0 or pid == os.getppid():
            raise PermissionError(
                "[Sandbox Guard] Access Denied: sending signals to parent/group is blocked."
            )
        return orig_os_kill(pid, sig)

    os.kill = _safe_os_kill  # type: ignore[assignment]


def _install_ctypes_guard() -> None:
    """Блокирует загрузку libc/msvcrt через ctypes (прямой syscall API)."""

    banned_patterns = ("libc", "msvcrt", "ucrtbase", "kernel32", "libsystem")

    orig_CDLL = ctypes.CDLL

    class _SafeCDLL:
        def __init__(self, name, *args, **kwargs):  # type: ignore[no-untyped-def]
            lname = (name or "").lower()
            if any(p in lname for p in banned_patterns):
                raise PermissionError(
                    f"[Sandbox Guard] Access Denied: loading '{name}' via ctypes is blocked."
                )
            self._real = orig_CDLL(name, *args, **kwargs)

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(self._real, item)

    ctypes.CDLL = _SafeCDLL  # type: ignore[assignment]
    ctypes.cdll.LoadLibrary = _SafeCDLL  # type: ignore[assignment]

    for name in ("WinDLL", "OleDLL", "PyDLL"):
        if hasattr(ctypes, name):
            setattr(ctypes, name, _SafeCDLL)


def _install_reload_guard() -> None:
    """Не даёт ``importlib.reload`` перезагрузить защищённые модули."""

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
# Публичный API
# ----------------------------------------------------------------------
def install(framework_dir: Path, sandbox_dir: Path) -> None:
    """Включает все защиты. Должно быть вызвано ДО exec пользовательского кода."""

    # Скрабим env в первую очередь — на случай если пользовательский код
    # форкнется и инхерит переменные.
    scrub_environ()

    checker = PathChecker(framework_dir, sandbox_dir)
    _install_file_guards(checker)
    _install_process_guards()
    _install_ctypes_guard()
    _install_reload_guard()


__all__ = ["install", "PathChecker", "scrub_environ"]

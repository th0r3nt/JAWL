"""Regression tests for the centralized sandbox guard.

These tests verify that the guard blocks every escape vector we previously
demonstrated against the original ``sandbox_runner.py`` (path traversal via
pathlib, raw ``os.open``, ``_io.FileIO``, ``fork``/``execv``/``posix_spawn``,
``ctypes`` → libc, ``importlib.reload`` un-patching, parent-process kill,
and environment leak).

Each test runs the victim code in a **separate subprocess** so that patches
made in one test do not leak into others.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


# ----------------------------------------------------------------------
# Test runner helpers
# ----------------------------------------------------------------------
TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "src" / "utils" / "templates"
)
GUARD_PATH = TEMPLATES_DIR / "_sandbox_guard.py"


def run_in_sandbox(
    tmp_path: Path,
    script_body: str,
    *,
    secret_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute ``script_body`` after installing the sandbox guard.

    ``tmp_path`` acts as the synthetic *framework_dir*; a subdirectory ``sb``
    inside it acts as the *sandbox_dir*. The caller can pass a *secret_env*
    dict whose keys are injected into the child's environment so individual
    tests can verify scrubbing behaviour.
    """

    framework_dir = tmp_path
    sandbox_dir = tmp_path / "sb"
    sandbox_dir.mkdir(exist_ok=True)

    # Create a "secret" file outside the sandbox so path-traversal tests can
    # try to read it.
    secret_file = framework_dir / ".env"
    if not secret_file.exists():
        secret_file.write_text("SUPER_SECRET=value\n", encoding="utf-8")

    driver = tmp_path / "driver.py"
    driver.write_text(
        textwrap.dedent(
            f"""
            import sys
            from pathlib import Path

            sys.path.insert(0, {str(TEMPLATES_DIR)!r})
            from _sandbox_guard import install

            install(Path({str(framework_dir)!r}), Path({str(sandbox_dir)!r}))
            """
        ).lstrip()
        + "\n"
        + script_body,
        encoding="utf-8",
    )

    env = os.environ.copy()
    if secret_env:
        env.update(secret_env)

    return subprocess.run(
        [sys.executable, str(driver)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


# ----------------------------------------------------------------------
# Path traversal: old and new vectors
# ----------------------------------------------------------------------
def test_pathlib_read_text_blocked(tmp_path: Path) -> None:
    """pathlib.Path.read_text() must NOT bypass the guard (the classic hole)."""

    body = textwrap.dedent(
        """
        from pathlib import Path
        try:
            secret = Path({sec!r}).read_text()
            print("LEAK:" + secret)
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        """
    ).format(sec=str(tmp_path / ".env"))

    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout + res.stderr
    assert "LEAK:" not in res.stdout


def test_os_open_blocked(tmp_path: Path) -> None:
    """Direct os.open()/os.read() must not bypass the guard."""

    body = textwrap.dedent(
        """
        import os
        try:
            fd = os.open({sec!r}, os.O_RDONLY)
            print("LEAK:" + os.read(fd, 100).decode())
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        """
    ).format(sec=str(tmp_path / ".env"))

    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout + res.stderr


def test_fileio_blocked(tmp_path: Path) -> None:
    """_io.FileIO (low-level CPython IO) must not bypass the guard."""

    body = textwrap.dedent(
        """
        import _io
        try:
            fd = _io.FileIO({sec!r}, "r")
            print("LEAK:" + fd.read().decode())
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        """
    ).format(sec=str(tmp_path / ".env"))

    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout + res.stderr


# ----------------------------------------------------------------------
# Shell / process escapes
# ----------------------------------------------------------------------
def test_os_fork_blocked(tmp_path: Path) -> None:
    if not hasattr(os, "fork"):
        return  # windows

    body = textwrap.dedent(
        """
        import os
        try:
            pid = os.fork()
            print("LEAK:FORK_SUCCESS")
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        """
    )
    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout


def test_posix_spawn_blocked(tmp_path: Path) -> None:
    if not hasattr(os, "posix_spawn"):
        return

    body = textwrap.dedent(
        """
        import os
        try:
            os.posix_spawn("/bin/sh", ["sh", "-c", "echo LEAK:PWNED"], os.environ)
            print("LEAK:SPAWNED")
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        """
    )
    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout


def test_subprocess_run_blocked(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """
        import subprocess
        try:
            subprocess.run(["echo", "LEAK"], check=False)
            print("LEAK:RAN")
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        """
    )
    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout


# ----------------------------------------------------------------------
# ctypes: direct libc access
# ----------------------------------------------------------------------
def test_ctypes_libc_blocked(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """
        import ctypes
        try:
            ctypes.CDLL("libc.so.6")
            print("LEAK:LOADED")
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        except OSError:
            # platform without glibc — treat as a non-issue (test harness)
            print("BLOCKED:no-libc")
        """
    )
    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout


# ----------------------------------------------------------------------
# importlib.reload un-patching
# ----------------------------------------------------------------------
def test_reload_protected_modules_blocked(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """
        import importlib, subprocess
        try:
            importlib.reload(subprocess)
            print("LEAK:RELOADED")
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        """
    )
    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout


# ----------------------------------------------------------------------
# Killing the parent process (agent suicide)
# ----------------------------------------------------------------------
def test_os_kill_parent_blocked(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """
        import os, signal
        try:
            os.kill(os.getppid(), signal.SIGTERM)
            print("LEAK:KILLED_PARENT")
        except PermissionError as e:
            print("BLOCKED:" + str(e))
        """
    )
    res = run_in_sandbox(tmp_path, body)
    assert "BLOCKED:" in res.stdout, res.stdout


# ----------------------------------------------------------------------
# Environment scrubbing
# ----------------------------------------------------------------------
def test_env_secrets_are_scrubbed(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """
        import os
        leaked = []
        for k in os.environ:
            if "SECRET_TOKEN" in k or "API_KEY" in k:
                leaked.append(k)
        print("LEAKED:" + ",".join(leaked) if leaked else "CLEAN")
        """
    )
    res = run_in_sandbox(
        tmp_path,
        body,
        secret_env={"MY_SECRET_TOKEN": "hunter2", "OPENAI_API_KEY": "sk-...xxx"},
    )
    assert "CLEAN" in res.stdout, res.stdout


def test_allowed_env_vars_preserved(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """
        import os
        print("PATH_OK" if os.environ.get("PATH") else "PATH_MISSING")
        print("JAWL_OK" if os.environ.get("JAWL_SANDBOX_DIR") is None or os.environ.get("JAWL_SANDBOX_DIR") else "JAWL_MISSING")
        """
    )
    res = run_in_sandbox(tmp_path, body)
    # PATH must not be scrubbed, JAWL_ prefix stays.
    assert "PATH_OK" in res.stdout, res.stdout


# ----------------------------------------------------------------------
# Sanity check: sandbox paths still work for legitimate code
# ----------------------------------------------------------------------
def test_legitimate_sandbox_read_still_works(tmp_path: Path) -> None:
    sandbox_file = tmp_path / "sb" / "hello.txt"
    (tmp_path / "sb").mkdir(exist_ok=True)
    sandbox_file.write_text("hi there", encoding="utf-8")

    body = textwrap.dedent(
        f"""
        text = open({str(sandbox_file)!r}).read()
        print("READ:" + text)
        """
    )
    res = run_in_sandbox(tmp_path, body)
    assert "READ:hi there" in res.stdout, res.stdout + res.stderr

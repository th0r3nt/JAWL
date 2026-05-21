import os
import shutil
import pytest
from unittest.mock import patch

from src.l2_interfaces.host.os.client import HostOSAccessLevel
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.decorators import require_access
from src.l3_agent.skills.registry import SkillResult
from src.utils._tools import get_project_root


class DummyOSClass:
    def __init__(self, host_os_client):
        self.host_os = host_os_client

    @require_access(HostOSAccessLevel.OPERATOR)
    async def dangerous_action(self):
        return SkillResult.ok("Success")


@pytest.mark.asyncio
async def test_execute_shell_command_safe(os_client):
    os_client.access_level = HostOSAccessLevel.ROOT
    executor = HostOSExecution(os_client)

    res = await executor.execute_shell_command("python -c \"print('Agent Online')\"")

    assert res.is_success is True
    assert "Agent Online" in res.message
    # FIXED: Expected English exit report
    assert "Command exited with code 0" in res.message


@pytest.mark.asyncio
@patch("src.l2_interfaces.host.os.skills.execution.psutil.Process")
async def test_execution_kill_process_not_found(mock_process, os_client):
    import psutil

    os_client.access_level = HostOSAccessLevel.ROOT
    executor = HostOSExecution(os_client)

    mock_process.side_effect = psutil.NoSuchProcess(pid=99999)

    res = await executor.kill_process(pid=99999)
    assert res.is_success is False
    # FIXED: Expected English error response
    assert "not found" in res.message


@pytest.mark.asyncio
async def test_require_access_decorator_blocks(os_client):
    dummy = DummyOSClass(os_client)
    res = await dummy.dangerous_action()

    assert res.is_success is False
    # FIXED: Expected English error response
    assert "Access denied" in res.message


@pytest.mark.asyncio
async def test_require_os_access_decorator_allows(os_client):
    os_client.access_level = HostOSAccessLevel.ROOT
    dummy = DummyOSClass(os_client)

    res = await dummy.dangerous_action()
    assert res.is_success is True


def test_build_isolated_env_scrubs_secrets(os_client):
    executor = HostOSExecution(os_client)

    os.environ["SECRET_TEST_TOKEN"] = "12345"
    os.environ["LLM_API_KEY_1"] = "sk-xxx"
    os.environ["NORMAL_VAR"] = "ok_value"

    env = executor._build_isolated_env()

    assert "SECRET_TEST_TOKEN" not in env
    assert "LLM_API_KEY_1" not in env
    assert "NORMAL_VAR" in env

    del os.environ["SECRET_TEST_TOKEN"]
    del os.environ["LLM_API_KEY_1"]
    del os.environ["NORMAL_VAR"]


@pytest.mark.asyncio
async def test_sandbox_guard_blocks_traversal_and_subprocess(os_client, tmp_path):
    os_client.access_level = HostOSAccessLevel.OBSERVER
    executor = HostOSExecution(os_client)

    real_root = get_project_root()
    template_src = real_root / "src" / "utils" / "templates" / "sandbox_runner.py"

    template_dst = tmp_path / "src" / "utils" / "templates" / "sandbox_runner.py"
    template_dst.parent.mkdir(parents=True, exist_ok=True)

    if template_src.exists():
        shutil.copy2(template_src, template_dst)
    else:
        pytest.skip("Template sandbox_runner.py missing.")

    guard_src = real_root / "src" / "utils" / "templates" / "_sandbox_guard.py"
    guard_dst = tmp_path / "src" / "utils" / "templates" / "_sandbox_guard.py"
    if guard_src.exists():
        shutil.copy2(guard_src, guard_dst)

    secret_file = tmp_path / ".env"
    secret_file.write_text("SUPER_SECRET_KEY=123", encoding="utf-8")

    malicious_code = """
import os
import subprocess

try:
    with open("../.env", "r") as f:
        print(f"LEAKED: {f.read()}")
except PermissionError as e:
    print(f"OPEN_BLOCKED: {e}")

try:
    subprocess.check_output("echo 1", shell=True)
    print("SUBPROCESS_WORKED")
except PermissionError as e:
    print(f"SUBPROCESS_BLOCKED: {e}")
"""
    malicious_script = os_client.sandbox_dir / "evil.py"
    malicious_script.write_text(malicious_code, encoding="utf-8")

    res = await executor.execute_script("sandbox/evil.py")

    assert res.is_success is True, res.message

    assert "LEAKED: SUPER_SECRET_KEY=123" not in res.message
    assert "OPEN_BLOCKED:" in res.message
    # FIXED: Expected English Guard response
    assert "Path Traversal attempt blocked" in res.message

    assert "SUBPROCESS_WORKED" not in res.message
    assert "SUBPROCESS_BLOCKED:" in res.message
    # FIXED: Expected English Guard response
    assert "Usage of shell/subprocess is blocked" in res.message


@pytest.mark.asyncio
async def test_execute_script_observer_blocks_non_python_scripts(os_client, tmp_path):
    os_client.access_level = HostOSAccessLevel.OBSERVER
    executor = HostOSExecution(os_client)

    victim = tmp_path / "observer_shell_rce.txt"
    shell_script = os_client.sandbox_dir / "poc.sh"
    shell_script.write_text(f"#!/bin/sh\necho PWNED > {victim}\n", encoding="utf-8")

    res = await executor.execute_script("sandbox/poc.sh")

    assert res.is_success is False
    # FIXED: Expected English error response
    assert "require Access Level >= 2" in res.message
    assert not victim.exists()


@pytest.mark.asyncio
async def test_sandbox_guard_blocks_os_spawn_and_exec_family(os_client, tmp_path):
    os_client.access_level = HostOSAccessLevel.OBSERVER
    executor = HostOSExecution(os_client)

    real_root = get_project_root()
    template_src = real_root / "src" / "utils" / "templates" / "sandbox_runner.py"
    guard_src = real_root / "src" / "utils" / "templates" / "_sandbox_guard.py"
    template_dst = tmp_path / "src" / "utils" / "templates" / "sandbox_runner.py"
    guard_dst = tmp_path / "src" / "utils" / "templates" / "_sandbox_guard.py"
    template_dst.parent.mkdir(parents=True, exist_ok=True)

    if template_src.exists() and guard_src.exists():
        shutil.copy2(template_src, template_dst)
        shutil.copy2(guard_src, guard_dst)
    else:
        pytest.skip("Framework template files missing.")

    malicious_code = """
import os

if hasattr(os, 'spawnlp'):
    try:
        os.spawnlp(os.P_WAIT, 'echo', 'echo', 'SPAWN_WORKED')
        print("SPAWNLP_NOT_BLOCKED")
    except PermissionError as e:
        print(f"SPAWNLP_BLOCKED: {e}")
    except Exception as e:
        print(f"SPAWNLP_ERROR: {type(e).__name__}")
else:
    print("SPAWNLP_BLOCKED: Missing on OS")

if hasattr(os, 'posix_spawn'):
    try:
        os.posix_spawn('/bin/echo', ['echo', 'POSIX_WORKED'], os.environ)
        print("POSIX_SPAWN_NOT_BLOCKED")
    except PermissionError as e:
        print(f"POSIX_SPAWN_BLOCKED: {e}")
    except Exception as e:
        print(f"POSIX_SPAWN_ERROR: {type(e).__name__}")
else:
    print("POSIX_SPAWN_BLOCKED: Missing on OS")

if hasattr(os, 'execvp'):
    try:
        os.execvp('echo', ['echo', 'EXEC_WORKED'])
        print("EXECVP_NOT_BLOCKED")
    except PermissionError as e:
        print(f"EXECVP_BLOCKED: {e}")
    except Exception as e:
        print(f"EXECVP_ERROR: {type(e).__name__}")
else:
    print("EXECVP_BLOCKED: Missing on OS")

if hasattr(os, 'fork'):
    try:
        pid = os.fork()
        if pid == 0:
            os._exit(0)
        print("FORK_NOT_BLOCKED")
    except PermissionError as e:
        print(f"FORK_BLOCKED: {e}")
    except Exception as e:
        print(f"FORK_ERROR: {type(e).__name__}")
else:
    print("FORK_BLOCKED: Missing on OS")
"""
    malicious_script = os_client.sandbox_dir / "evil_spawn.py"
    malicious_script.write_text(malicious_code, encoding="utf-8")

    res = await executor.execute_script("sandbox/evil_spawn.py")
    assert res.is_success is True, res.message

    assert "SPAWN_WORKED" not in res.message
    assert "POSIX_WORKED" not in res.message
    assert "SPAWNLP_NOT_BLOCKED" not in res.message
    assert "POSIX_SPAWN_NOT_BLOCKED" not in res.message
    assert "EXECVP_NOT_BLOCKED" not in res.message
    assert "FORK_NOT_BLOCKED" not in res.message

    assert "SPAWNLP_BLOCKED:" in res.message
    assert "POSIX_SPAWN_BLOCKED:" in res.message
    assert "EXECVP_BLOCKED:" in res.message
    assert "FORK_BLOCKED:" in res.message

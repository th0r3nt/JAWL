"""
Skills for executing computational operations: launching scripts, daemons, and raw shell commands.
This is the most critical module from a security standpoint. Contains environment cleaning
logic to scrub secrets prior to spawning subprocesses, and Sandbox Guard injection.
"""

import asyncio
import sys
import os
import psutil
import json
import time
import subprocess
import uuid
import traceback

from src.utils.logger import main_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.swarm.roles import Subagents
from src.l3_agent.skills.registry import SkillResult, skill


class HostOSExecution:
    """
    Agent skills for executing code and process orchestration.
    Highly sensitive module controlled by the operating system Gatekeeper.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    def _kill_process_tree(self, pid: int) -> None:
        """
        Recursively terminates the entire process tree (parent and all descendants).
        Prevents communicate() from hanging if child processes (such as Node)
        hold open file descriptors after parent death.
        """

        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)

            for child in children:
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            parent.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def _build_isolated_env(self) -> dict:
        """
        Constructs an isolated environment dict for sandbox child processes.
        Scrubs system sensitive API keys and secrets.
        """

        env = os.environ.copy()

        # Rigid scrubbing of framework secrets from child process
        forbidden_substrings = [
            "TOKEN",
            "KEY",
            "SECRET",
            "PASSWORD",
            "HASH",
            "API_ID",
            "CREDENTIALS",
            "URL",
            "URI",
            "JAWL",
        ]
        for k in list(env.keys()):
            if any(sub in k.upper() for sub in forbidden_substrings):
                del env[k]

        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        fw_dir = str(self.host_os.framework_dir.resolve())
        sb_dir = str(self.host_os.sandbox_dir.resolve())
        sys_dir = str(self.host_os.system_dir.resolve())

        env["JAWL_FRAMEWORK_DIR"] = fw_dir
        env["JAWL_SANDBOX_DIR"] = sb_dir

        paths_to_add = [fw_dir, sb_dir, sys_dir]

        current_pythonpath = env.get("PYTHONPATH", "")
        if current_pythonpath:
            for p in current_pythonpath.split(os.pathsep):
                if p and p not in paths_to_add:
                    paths_to_add.append(p)

        env["PYTHONPATH"] = os.pathsep.join(paths_to_add)
        return env

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def execute_script(self, filepath: str) -> SkillResult:
        """
        Runs script in isolated environment. Captures STDOUT/STDERR.

        filepath: Rel/abs path.
        """

        timeout = self.host_os.config.execution_timeout_sec

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if (
                self.host_os.access_level < HostOSAccessLevel.OPERATOR
                and not safe_path.is_relative_to(self.host_os.sandbox_dir)
            ):
                return SkillResult.fail(
                    "Access denied: with the current privilege level, scripts must be executed strictly from the sandbox/ folder."
                )

            if not safe_path.is_file():
                return SkillResult.fail(f"Error: Script file not found ({safe_path.name}).")

            ext = safe_path.suffix.lower()
            if self.host_os.access_level < HostOSAccessLevel.OPERATOR and ext != ".py":
                return SkillResult.fail(
                    "Access denied: with the current privilege level, only Python scripts can be executed "
                    "via sandbox guard. Shell/JS/native scripts require Access Level >= 2 (OPERATOR)."
                )

            env = self._build_isolated_env()
            env["JAWL_TARGET_SCRIPT"] = str(safe_path)

            if ext == ".py":
                runner_path = (
                    self.host_os.framework_dir
                    / "src"
                    / "utils"
                    / "templates"
                    / "sandbox_runner.py"
                )

                if runner_path.exists():
                    cmd = [sys.executable, str(runner_path)]
                else:
                    cmd = [sys.executable, str(safe_path)]

            elif ext == ".sh":
                import shutil

                shell_exec = "bash" if shutil.which("bash") else "sh"
                cmd = [shell_exec, str(safe_path)]

            elif ext in (".bat", ".cmd"):
                cmd = ["cmd.exe", "/c", str(safe_path)]

            elif ext == ".js":
                cmd = ["node", str(safe_path)]

            else:
                cmd = [str(safe_path)]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(safe_path.parent),
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                self._kill_process_tree(process.pid)
                await process.wait()
                return SkillResult.fail(
                    f"The script ran longer than {timeout} seconds, and its entire process tree was forcibly killed (Timeout)."
                )

            stdout_str = truncate_text(
                stdout.decode("utf-8", errors="replace").strip(), max_chars=5000
            )
            stderr_str = truncate_text(
                stderr.decode("utf-8", errors="replace").strip(), max_chars=5000
            )

            exit_code = process.returncode
            main_logger.info(f"[Host OS] Executed script {safe_path.name} (Code: {exit_code})")

            report = f"Script exited with code {exit_code}."
            if stdout_str:
                report += f"\n\nSTDOUT:\n```\n{stdout_str}\n```"

            if stderr_str:
                report += f"\n\nSTDERR:\n```\n{stderr_str}\n```"

            return SkillResult.ok(report)

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            err_msg = (
                f"Critical error running script: {e}\n\nTraceback:\n{traceback.format_exc()}"
            )
            main_logger.error(f"[Host OS] {err_msg}")
            return SkillResult.fail(err_msg)

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.ROOT)
    async def execute_shell_command(self, command: str) -> SkillResult:
        """
        Executes raw bash/cmd command in host OS terminal.
        """

        cmd_lower = command.lower()
        if "taskkill" in cmd_lower or "kill" in cmd_lower or "pkill" in cmd_lower:
            if "python" in cmd_lower or "jawl" in cmd_lower:
                return SkillResult.fail(
                    "SYSTEM DENIED: Attempt to terminate the system python process. This command may stop the main framework system. This action is blocked for security reasons."
                )

        timeout = self.host_os.config.execution_timeout_sec

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.host_os.sandbox_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

            except asyncio.TimeoutError:
                self._kill_process_tree(process.pid)
                await process.wait()
                return SkillResult.fail(
                    f"The command ran longer than {timeout} seconds, and its entire process tree was killed (Timeout)."
                )

            stdout_str = truncate_text(
                stdout.decode("utf-8", errors="replace").strip(), max_chars=5000
            )
            stderr_str = truncate_text(
                stderr.decode("utf-8", errors="replace").strip(), max_chars=5000
            )

            exit_code = process.returncode
            main_logger.info(f"[Host OS] Executed shell command (Code: {exit_code})")

            report = f"Command exited with code {exit_code}."
            if stdout_str:
                report += f"\n\nSTDOUT:\n{stdout_str}"
            if stderr_str:
                report += f"\n\nSTDERR:\n{stderr_str}"

            return SkillResult.ok(report)

        except Exception as e:
            return SkillResult.fail(f"Error executing shell command: {e}")

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def run_pytest(self, target_path: str = "tests/") -> SkillResult:
        """
        Runs pytest.

        target_path: File/dir path (default 'tests/').
        """
        try:
            safe_path = self.host_os.validate_path(target_path, is_write=False)

            if not safe_path.exists():
                return SkillResult.fail(f"Path not found: {safe_path.name}")

            cmd = [sys.executable, "-m", "pytest", str(safe_path), "-v", "--disable-warnings"]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.host_os.framework_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except asyncio.TimeoutError:
                self._kill_process_tree(process.pid)
                return SkillResult.fail(
                    "Tests ran longer than 120 seconds and were aborted (Timeout)."
                )

            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()

            full_log = f"{out_str}\n{err_str}".strip()
            clean_log = full_log[-4000:] if len(full_log) > 4000 else full_log

            exit_code = process.returncode
            main_logger.info(
                f"[Host OS] Executed run_pytest for {safe_path.name} (Code: {exit_code})"
            )

            if exit_code == 0:
                return SkillResult.ok(
                    f"Tests passed successfully.\n\nLog:\n```\n{clean_log}\n```"
                )
            else:
                return SkillResult.fail(
                    f"Tests failed (Code {exit_code}).\n\nLog (last lines):\n```\n{clean_log}\n```"
                )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Critical error running pytest: {e}")

    @skill(swarm=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.ROOT)
    async def kill_process(self, pid: int) -> SkillResult:
        """
        Forcefully terminates OS process.
        """

        try:
            process = psutil.Process(int(pid))
            process_name = process.name()

            process.terminate()
            process.wait(timeout=3)

            main_logger.info(f"[Host OS] Terminated process {pid} ({process_name})")
            return SkillResult.ok(f"Process {pid} ({process_name}) successfully terminated.")

        except psutil.NoSuchProcess:
            return SkillResult.fail(f"Error: Process with PID {pid} not found.")

        except psutil.AccessDenied:
            return SkillResult.fail(
                f"Access denied (OS did not allow terminating process {pid})."
            )

        except psutil.TimeoutExpired:
            self._kill_process_tree(int(pid))
            return SkillResult.ok(
                f"Process {pid} hung and its entire tree was killed forcibly (kill)."
            )

        except Exception as e:
            return SkillResult.fail(f"Error attempting to terminate process: {e}")

    @skill(swarm=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def start_daemon(self, filepath: str, name: str, description: str) -> SkillResult:
        """
        Starts Python script as background daemon.
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Error: Script not found ({safe_path.name}).")

            if safe_path.suffix.lower() != ".py":
                return SkillResult.fail("Error: Only .py scripts are supported as daemons.")

            safe_name = "".join(c if c.isalnum() else "_" for c in name)
            logs_dir = self.host_os.system_dir / "logs"
            logs_dir.mkdir(exist_ok=True)

            log_path = logs_dir / f"{safe_name}.log"
            log_file = open(log_path, "a", encoding="utf-8")

            env = self._build_isolated_env()
            env["JAWL_TARGET_SCRIPT"] = str(safe_path)

            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
            else:
                kwargs["start_new_session"] = True

            runner_path = (
                self.host_os.framework_dir
                / "src"
                / "utils"
                / "templates"
                / "sandbox_runner.py"
            )
            if runner_path.exists():
                cmd = [sys.executable, str(runner_path)]
            else:
                cmd = [sys.executable, str(safe_path)]

            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=str(safe_path.parent),
                env=env,
                **kwargs,
            )

            pid = process.pid

            registry = self.host_os.get_daemons_registry()
            registry[str(pid)] = {
                "name": name,
                "description": description,
                "filepath": str(safe_path.relative_to(self.host_os.sandbox_dir)),
                "start_time": time.time(),
            }
            self.host_os.set_daemons_registry(registry)

            main_logger.info(f"[Host OS] Background daemon '{name}' started (PID: {pid})")

            return SkillResult.ok(
                f"Daemon '{name}' successfully started (PID: {pid}).\n"
                f"Logs redirected to: sandbox/_system/logs/{log_path.name}\n"
                f"You can now track its status in the Host OS context."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error starting daemon: {e}")

    @skill(swarm=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def stop_daemon(self, pid: int) -> SkillResult:
        """
        Stops running background daemon by PID.
        """
        try:
            registry = self.host_os.get_daemons_registry()
            pid_str = str(pid)

            if pid_str not in registry:
                return SkillResult.fail(f"Error: Daemon with PID {pid} not found in registry.")

            name = registry[pid_str]["name"]

            try:
                proc = psutil.Process(int(pid))
                proc.terminate()
                proc.wait(timeout=3)

            except psutil.NoSuchProcess:
                pass

            except psutil.TimeoutExpired:
                self._kill_process_tree(int(pid))

            except Exception as e:
                return SkillResult.fail(f"Failed to terminate process: {e}")

            del registry[pid_str]
            self.host_os.set_daemons_registry(registry)

            main_logger.info(f"[Host OS] Background daemon '{name}' stopped (PID: {pid})")
            return SkillResult.ok(
                f"Daemon '{name}' (PID: {pid}) successfully stopped manually."
            )

        except Exception as e:
            return SkillResult.fail(f"Error stopping daemon: {e}")

    @skill()
    @require_access(HostOSAccessLevel.OBSERVER)
    async def execute_sandbox_func(
        self, filepath: str, func_name: str, kwargs: dict = None
    ) -> SkillResult:
        """
        Isolated RPC call. Dynamically executes specific function in sandbox Python script.

        filepath: .py path.
        func_name: Target function.
        kwargs: Named arguments dict.
        """

        if not isinstance(kwargs, dict):
            kwargs = {}

        timeout = self.host_os.config.execution_timeout_sec

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file() or safe_path.suffix.lower() != ".py":
                return SkillResult.fail(
                    f"Error: File not found or is not a .py script ({safe_path.name})."
                )

            tmp_dir = self.host_os.system_dir / ".tmp"
            tmp_dir.mkdir(exist_ok=True)

            wrapper_id = str(uuid.uuid4())[:8]
            wrapper_path = tmp_dir / f"rpc_wrapper_{wrapper_id}.py"

            template_path = (
                self.host_os.framework_dir / "src" / "utils" / "templates" / "rpc_wrapper.py"
            )
            if not template_path.exists():
                return SkillResult.fail(
                    "System error: RPC wrapper template not found (src/utils/templates/rpc_wrapper.py)."
                )

            wrapper_code = template_path.read_text(encoding="utf-8")
            wrapper_path.write_text(wrapper_code, encoding="utf-8")

            env = self._build_isolated_env()

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(wrapper_path),
                str(safe_path),
                func_name,
                str(self.host_os.sandbox_dir.resolve()),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.host_os.sandbox_dir),
                env=env,
            )

            stdin_data = json.dumps(kwargs, ensure_ascii=False).encode("utf-8")

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=stdin_data), timeout=timeout
                )

            except asyncio.TimeoutError:
                self._kill_process_tree(process.pid)
                await process.wait()
                wrapper_path.unlink(missing_ok=True)
                return SkillResult.fail(
                    f"The function ran longer than {timeout} seconds, and its entire process tree was killed (Timeout)."
                )

            wrapper_path.unlink(missing_ok=True)

            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()

            rpc_prefix = "---RPC_RESULT---"
            if rpc_prefix in out_str:
                parts = out_str.split(rpc_prefix)
                script_stdout = parts[0].strip()
                rpc_json_str = parts[1].strip()

                try:
                    rpc_result = json.loads(rpc_json_str)
                except json.JSONDecodeError:
                    return SkillResult.fail(
                        f"Script executed but result is invalid.\nSTDOUT:\n{out_str}\nSTDERR:\n{err_str}"
                    )

                report = []
                if script_stdout:
                    report.append(
                        f"Script STDOUT:\n```\n{truncate_text(script_stdout, 2000)}\n```"
                    )
                if err_str:
                    report.append(f"Script STDERR:\n```\n{truncate_text(err_str, 2000)}\n```")

                if rpc_result.get("status") == "ok":
                    result_data = rpc_result.get("result")
                    report.append(
                        f"Returned result (Return):\n```json\n{json.dumps(result_data, ensure_ascii=False, indent=2)}\n```"
                    )
                    main_logger.info(
                        f"[Host OS] RPC-gateway successfully executed function '{func_name}' from {safe_path.name}"
                    )
                    return SkillResult.ok("\n\n".join(report))

                else:
                    err_msg = rpc_result.get("error")
                    tb = rpc_result.get("traceback")
                    report.append(
                        f"Error executing '{func_name}': {err_msg}\n\nTraceback:\n```python\n{tb}\n```"
                    )
                    return SkillResult.fail("\n\n".join(report))
            else:
                return SkillResult.fail(
                    f"Script ended with error (code {process.returncode}).\n"
                    f"STDOUT:\n{truncate_text(out_str, 2000)}\n"
                    f"STDERR:\n{truncate_text(err_str, 2000)}"
                )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            err_msg = f"Internal RPC error: {e}\n\nTraceback:\n{traceback.format_exc()}"
            main_logger.error(f"[Host OS] {err_msg}")
            return SkillResult.fail(err_msg)

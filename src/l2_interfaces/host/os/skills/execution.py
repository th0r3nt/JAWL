"""
Навыки для выполнения вычислительных операций: запуск скриптов, демонов и сырых shell-команд.
Наиболее критичный модуль с точки зрения безопасности. Содержит логику "очистки" переменных
окружения от токенов перед спавном подпроцессов и инъекцию Sandbox Guard.
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

from src.utils.logger import system_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.swarm.roles import Subagents
from src.l3_agent.skills.registry import SkillResult, skill


class HostOSExecution:
    """
    Навыки агента для запуска кода и управления процессами.
    Самый опасный модуль: строго контролируется через Access Level.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    def _kill_process_tree(self, pid: int) -> None:
        """
        Рекурсивно убивает всё дерево процессов (родителя и всех потомков).
        Необходимо для предотвращения зависания communicate(), если дочерние
        процессы (например node) удерживают открытые пайпы (stdout/stderr) после смерти родителя.
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
        Собирает изолированное окружение (env) для запуска скриптов.
        Очищает окружение от системных секретов (чтобы хитрые агенты не достали их через os.environ).
        """

        env = os.environ.copy()

        # ЖЕСТКИЙ скраббинг секретов фреймворка из дочернего процесса
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
        env["PYTHONIOENCODING"] = "utf-8"

        fw_dir = str(self.host_os.framework_dir.resolve())
        sb_dir = str(self.host_os.sandbox_dir.resolve())
        sys_dir = str(self.host_os.system_dir.resolve())

        # Переменные для нашего Sandbox Runner (Гарда)
        env["JAWL_FRAMEWORK_DIR"] = fw_dir
        env["JAWL_SANDBOX_DIR"] = sb_dir

        # Добавляем все директории, чтобы 'import framework_api' работало как и раньше
        paths_to_add = [fw_dir, sb_dir, sys_dir]

        current_pythonpath = env.get("PYTHONPATH", "")
        if current_pythonpath:
            for p in current_pythonpath.split(os.pathsep):
                if p and p not in paths_to_add:
                    paths_to_add.append(p)

        env["PYTHONPATH"] = os.pathsep.join(paths_to_add)
        return env

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def execute_script(self, filepath: str) -> SkillResult:
        """
        Запускает скрипт (.py, .sh, .bat, .js) в изолированном окружении.
        Автоматически перехватывает STDOUT и STDERR. При превышении execution_timeout_sec
        жестко убивает всё дерево порожденных процессов (включая зомби).

        Args:
            filepath: Относительный или абсолютный путь к скрипту.
        """

        timeout = self.host_os.config.execution_timeout_sec

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if (
                self.host_os.access_level < HostOSAccessLevel.OPERATOR
                and not safe_path.is_relative_to(self.host_os.sandbox_dir)
            ):
                return SkillResult.fail(
                    "Отказано в доступе: при текущем уровне прав скрипты можно запускать строго из папки sandbox/."
                )

            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл скрипта не найден ({safe_path.name}).")

            # Формируем изолированное окружение
            env = self._build_isolated_env()
            env["JAWL_TARGET_SCRIPT"] = str(safe_path)

            ext = safe_path.suffix.lower()

            if ext == ".py":
                # Внедряем безопасную обертку (Guard)
                runner_path = (
                    self.host_os.framework_dir
                    / "src"
                    / "utils"
                    / "templates"
                    / "sandbox_runner.py"
                )

                # Если обертка существует - используем ее, иначе fallback на стандартный запуск
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
                    f"Скрипт работал дольше {timeout} секунд и всё его дерево процессов было принудительно убито (Таймаут)."
                )

            stdout_str = truncate_text(
                stdout.decode("utf-8", errors="replace").strip(), max_chars=5000
            )
            stderr_str = truncate_text(
                stderr.decode("utf-8", errors="replace").strip(), max_chars=5000
            )

            exit_code = process.returncode
            system_logger.info(
                f"[Host OS] Выполнен скрипт {safe_path.name} (Код: {exit_code})"
            )

            report = f"Скрипт завершился с кодом {exit_code}."
            if stdout_str:
                report += f"\n\nSTDOUT:\n```\n{stdout_str}\n```"

            if stderr_str:
                report += f"\n\nSTDERR:\n```\n{stderr_str}\n```"

            return SkillResult.ok(report)

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            err_msg = f"Критическая ошибка при запуске скрипта: {e}\n\nTraceback:\n{traceback.format_exc()}"
            system_logger.error(f"[Host OS] {err_msg}")
            return SkillResult.fail(err_msg)

    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.ROOT)
    async def execute_shell_command(self, command: str) -> SkillResult:
        """
        [3/ROOT] Запускает сырую bash/cmd команду в терминале ОС.
        """

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
                    f"Команда работала дольше {timeout} секунд и всё её дерево процессов было убито (Таймаут)."
                )

            stdout_str = truncate_text(
                stdout.decode("utf-8", errors="replace").strip(), max_chars=5000
            )
            stderr_str = truncate_text(
                stderr.decode("utf-8", errors="replace").strip(), max_chars=5000
            )

            exit_code = process.returncode
            system_logger.info(f"[Host OS] Выполнена shell-команда (Код: {exit_code})")

            report = f"Команда завершилась с кодом {exit_code}."
            if stdout_str:
                report += f"\n\nSTDOUT:\n{stdout_str}"
            if stderr_str:
                report += f"\n\nSTDERR:\n{stderr_str}"

            return SkillResult.ok(report)

        except Exception as e:
            return SkillResult.fail(f"Ошибка выполнения shell-команды: {e}")
        
    @skill(swarm_roles=[Subagents.CODER, Subagents.QA_ENGINEER])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def run_pytest(self, target_path: str = "tests/") -> SkillResult:
        """
        Рабочий запуск тестирования (pytest) для проверки архитектуры 
        или запуска написанных тестов. Выполняется в нативном окружении ОС (без ограничений песочницы).

        Args:
            target_path: Путь к конкретному файлу или директории (по умолчанию 'tests/').
        """
        try:
            safe_path = self.host_os.validate_path(target_path, is_write=False)
            
            if not safe_path.exists():
                return SkillResult.fail(f"Путь не найден: {safe_path.name}")

            cmd = [sys.executable, "-m", "pytest", str(safe_path), "-v", "--disable-warnings"]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.host_os.framework_dir)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except asyncio.TimeoutError:
                self._kill_process_tree(process.pid)
                return SkillResult.fail("Тесты выполнялись дольше 120 секунд и были прерваны (Таймаут).")

            # Pytest часто пишет полезный вывод и в stdout, и в stderr. Собираем всё
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()
            
            full_log = f"{out_str}\n{err_str}".strip()
            # Берем хвост лога, так как там самая важная сводка (Traceback)
            clean_log = full_log[-4000:] if len(full_log) > 4000 else full_log
            
            exit_code = process.returncode
            system_logger.info(f"[Host OS] Выполнен run_pytest для {safe_path.name} (Код: {exit_code})")

            if exit_code == 0:
                return SkillResult.ok(f"Тесты успешно пройдены.\n\nЛог:\n```\n{clean_log}\n```")
            else:
                return SkillResult.fail(f"Тесты провалены (Код {exit_code}).\n\nЛог (последние строки):\n```\n{clean_log}\n```")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Критическая ошибка при запуске pytest: {e}")

    @skill(swarm_roles=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.ROOT)
    async def kill_process(self, pid: int) -> SkillResult:
        """
        [3/ROOT] Принудительно завершает процесс ОС по его PID.
        """

        try:
            process = psutil.Process(int(pid))
            process_name = process.name()

            process.terminate()
            process.wait(timeout=3)

            system_logger.info(f"[Host OS] Убит процесс {pid} ({process_name})")
            return SkillResult.ok(f"Процесс {pid} ({process_name}) успешно завершен.")

        except psutil.NoSuchProcess:
            return SkillResult.fail(f"Ошибка: Процесс с PID {pid} не найден.")

        except psutil.AccessDenied:
            return SkillResult.fail(
                f"Отказано в доступе (ОС не позволила убить процесс {pid})."
            )

        except psutil.TimeoutExpired:
            self._kill_process_tree(int(pid))
            return SkillResult.ok(
                f"Процесс {pid} завис и всё его дерево было убито принудительно (kill)."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при попытке завершить процесс: {e}")

    @skill(swarm_roles=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def start_daemon(self, filepath: str, name: str, description: str) -> SkillResult:
        """
        [1/OBSERVER] Запускает Python-скрипт как фоновый процесс (демон).
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Скрипт не найден ({safe_path.name}).")

            if safe_path.suffix.lower() != ".py":
                return SkillResult.fail(
                    "Ошибка: В качестве демонов поддерживается запуск только .py скриптов."
                )

            safe_name = "".join(c if c.isalnum() else "_" for c in name)
            logs_dir = self.host_os.system_dir / "logs"
            logs_dir.mkdir(exist_ok=True)

            log_path = logs_dir / f"daemon_{safe_name}.log"
            log_file = open(log_path, "a", encoding="utf-8")

            # Формируем изолированное окружение
            env = self._build_isolated_env()
            env["JAWL_TARGET_SCRIPT"] = str(safe_path)

            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
            else:
                kwargs["start_new_session"] = True

            # Запускаем через Guard
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

            system_logger.info(f"[Host OS] Запущен фоновый демон '{name}' (PID: {pid})")

            return SkillResult.ok(
                f"Демон '{name}' успешно запущен (PID: {pid}).\n"
                f"Логи перенаправлены в файл: sandbox/_system/logs/{log_path.name}\n"
                f"Теперь можно отслеживать его статус в контексте Host OS."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при запуске демона: {e}")

    @skill(swarm_roles=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def stop_daemon(self, pid: int) -> SkillResult:
        """
        [1/OBSERVER] Останавливает работающий фоновый демон по его PID.
        """
        try:
            registry = self.host_os.get_daemons_registry()
            pid_str = str(pid)

            if pid_str not in registry:
                return SkillResult.fail(f"Ошибка: Демон с PID {pid} не найден в реестре.")

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
                return SkillResult.fail(f"Не удалось завершить процесс: {e}")

            del registry[pid_str]
            self.host_os.set_daemons_registry(registry)

            system_logger.info(f"[Host OS] Остановлен фоновый демон '{name}' (PID: {pid})")
            return SkillResult.ok(f"Демон '{name}' (PID: {pid}) успешно остановлен вручную.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при остановке демона: {e}")

    @skill()
    @require_access(HostOSAccessLevel.OBSERVER)
    async def execute_sandbox_func(
        self, filepath: str, func_name: str, kwargs: dict = None
    ) -> SkillResult:
        """
        Изолированный RPC-вызов. Позволяет инамически запустить конкретную функцию
        внутри Python-скрипта в песочнице, передать ей аргументы и получить ответ.

        Args:
            filepath: Путь к .py скрипту.
            func_name: Имя вызываемой функции внутри скрипта.
            kwargs: Словарь именованных аргументов для передачи в функцию.
        """

        if not isinstance(kwargs, dict):
            kwargs = {}

        timeout = self.host_os.config.execution_timeout_sec

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file() or safe_path.suffix.lower() != ".py":
                return SkillResult.fail(
                    f"Ошибка: Файл не найден или это не .py скрипт ({safe_path.name})."
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
                    "Системная ошибка: Шаблон RPC-обертки не найден (src/utils/templates/rpc_wrapper.py)."
                )

            wrapper_code = template_path.read_text(encoding="utf-8")
            wrapper_path.write_text(wrapper_code, encoding="utf-8")

            # Формируем изолированное окружение
            env = self._build_isolated_env()

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(wrapper_path),
                str(safe_path),
                func_name,
                str(
                    self.host_os.sandbox_dir.resolve()
                ),  # Передаем корень песочницы для резолва путей
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
                    f"Функция работала дольше {timeout} секунд и всё дерево процессов было убито (Таймаут)."
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
                        f"Скрипт отработал, но результат невалиден.\nSTDOUT:\n{out_str}\nSTDERR:\n{err_str}"
                    )

                report = []
                if script_stdout:
                    report.append(
                        f"STDOUT скрипта:\n```\n{truncate_text(script_stdout, 2000)}\n```"
                    )
                if err_str:
                    report.append(f"STDERR скрипта:\n```\n{truncate_text(err_str, 2000)}\n```")

                if rpc_result.get("status") == "ok":
                    result_data = rpc_result.get("result")
                    report.append(
                        f"Возвращенный результат (Return):\n```json\n{json.dumps(result_data, ensure_ascii=False, indent=2)}\n```"
                    )
                    system_logger.info(
                        f"[Host OS] RPC-шлюз успешно выполнил функцию '{func_name}' из {safe_path.name}"
                    )
                    return SkillResult.ok("\n\n".join(report))

                else:
                    err_msg = rpc_result.get("error")
                    tb = rpc_result.get("traceback")
                    report.append(
                        f"Ошибка выполнения '{func_name}': {err_msg}\n\nTraceback:\n```python\n{tb}\n```"
                    )
                    return SkillResult.fail("\n\n".join(report))
            else:
                return SkillResult.fail(
                    f"Скрипт завершился с ошибкой (код {process.returncode}).\n"
                    f"STDOUT:\n{truncate_text(out_str, 2000)}\n"
                    f"STDERR:\n{truncate_text(err_str, 2000)}"
                )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            err_msg = f"Внутренняя ошибка RPC: {e}\n\nTraceback:\n{traceback.format_exc()}"
            system_logger.error(f"[Host OS] {err_msg}")
            return SkillResult.fail(err_msg)

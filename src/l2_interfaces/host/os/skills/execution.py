import asyncio
import sys
import psutil
import json
import uuid

from src.utils.logger import system_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSExecution:
    """
    Навыки агента для запуска кода и управления процессами.
    Самый опасный модуль: строго контролируется через Access Level.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    async def execute_script(self, filepath: str) -> SkillResult:
        """
        Запускает скрипт (.py, .sh, .bat, .js).
        При Access level = 1 запускает только из папки sandbox/.
        """

        timeout = self.host_os.config.execution_timeout_sec

        if self.host_os.access_level < HostOSAccessLevel.OBSERVER:
            return SkillResult.fail(
                "Отказано в доступе: выполнение скриптов разрешено при Access Level >= 1."
            )

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

            # Определяем интерпретатор по расширению
            ext = safe_path.suffix.lower()

            if ext == ".py":
                cmd = [sys.executable, str(safe_path)]

            elif ext == ".sh":
                # Fallback: используем 'sh', который есть в 100% UNIX-систем,
                # если скрипт вдруг попадет на Alpine Linux
                import shutil

                shell_exec = "bash" if shutil.which("bash") else "sh"
                cmd = [shell_exec, str(safe_path)]

            elif ext in (".bat", ".cmd"):
                cmd = ["cmd.exe", "/c", str(safe_path)]

            elif ext == ".js":
                cmd = ["node", str(safe_path)]

            else:
                # Пытаемся запустить как бинарник
                cmd = [str(safe_path)]

            # Асинхронный запуск подпроцесса
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(safe_path.parent),
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return SkillResult.fail(
                    f"Скрипт работал дольше {timeout} секунд и был принудительно убит (Таймаут)."
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

            # Формируем красивый вывод
            report = f"Скрипт завершился с кодом {exit_code}."
            if stdout_str:
                report += f"\n\nSTDOUT:\n```\n{stdout_str}\n```"
            if stderr_str:
                report += f"\n\nSTDERR:\n```\n{stderr_str}\n```"

            return SkillResult.ok(report)

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Критическая ошибка при запуске скрипта: {e}")

    @skill()
    async def execute_shell_command(self, command: str) -> SkillResult:
        """
        Запускает сырую bash/cmd команду в терминале ОС.
        Доступно только при Access Level >= 2.
        """

        timeout = self.host_os.config.execution_timeout_sec

        if self.host_os.access_level < HostOSAccessLevel.OPERATOR:
            return SkillResult.fail(
                "Отказано в доступе: выполнение shell-команд требует access_level >= 2 (OPERATOR)."
            )

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(
                    self.host_os.sandbox_dir
                ),  # По умолчанию открываем терминал в песочнице
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return SkillResult.fail(
                    f"Команда работала дольше {timeout} секунд и была убита (Таймаут)."
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

    @skill()
    async def kill_process(self, pid: int) -> SkillResult:
        """
        Принудительно завершает процесс ОС по его PID.
        Доступно только при Access Level >= 2.
        """

        if self.host_os.access_level < HostOSAccessLevel.OPERATOR:
            return SkillResult.fail(
                "Отказано в доступе: управление процессами ОС требует access_level >= 2 (OPERATOR)."
            )

        try:
            process = psutil.Process(pid)
            process_name = process.name()

            process.terminate()
            process.wait(timeout=3)  # Даем 3 секунды на корректное завершение

            system_logger.info(f"[Host OS] Убит процесс {pid} ({process_name})")
            return SkillResult.ok(f"Процесс {pid} ({process_name}) успешно завершен.")

        except psutil.NoSuchProcess:
            return SkillResult.fail(f"Ошибка: Процесс с PID {pid} не найден.")

        except psutil.AccessDenied:
            return SkillResult.fail(
                f"Отказано в доступе (ОС не позволила убить процесс {pid})."
            )

        except psutil.TimeoutExpired:
            # Если terminate() не помог, бьем кувалдой к чертям
            process.kill()
            return SkillResult.ok(f"Процесс {pid} завис и был убит принудительно (kill).")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при попытке завершить процесс: {e}")


    @skill()
    async def start_daemon(self, filepath: str, name: str, description: str) -> SkillResult:
        """
        Запускает Python-скрипт как фоновый процесс (демон).
        Скрипт будет работать автономно. Его вывод (print, ошибки) будет перенаправлен в файл daemon_<name>.log в песочнице.

        Можно использовать 'jawl_api.py' внутри скрипта для отправки событий (вебхуков) агенту. Пример:
        from jawl_api import send_event
        send_event("Парсинг окончен", {"new_items": 15})
        """
        import time
        import subprocess
        
        if self.host_os.access_level < HostOSAccessLevel.OBSERVER:
            return SkillResult.fail("Отказано в доступе: запуск демонов разрешен при Access Level >= 1.")

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Скрипт не найден ({safe_path.name}).")
                
            if safe_path.suffix.lower() != ".py":
                return SkillResult.fail("Ошибка: В качестве демонов поддерживается запуск только .py скриптов.")

            # Лог-файл для STDOUT/STDERR демона
            safe_name = "".join(c if c.isalnum() else "_" for c in name)
            
            # Складируем логи в отдельную папку sandbox/logs/
            logs_dir = self.host_os.sandbox_dir / "logs"
            logs_dir.mkdir(exist_ok=True)
            
            log_path = logs_dir / f"daemon_{safe_name}.log"
            log_file = open(log_path, "a", encoding="utf-8")

            # Параметры отсоединения процесса
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
            else:
                kwargs["start_new_session"] = True

            cmd = [sys.executable, str(safe_path)]
            
            # Запускаем неблокирующе
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=str(safe_path.parent),
                **kwargs
            )
            
            pid = process.pid
            
            # Сохраняем в реестр
            registry = self.host_os.get_daemons_registry()
            registry[str(pid)] = {
                "name": name,
                "description": description,
                "filepath": str(safe_path.relative_to(self.host_os.sandbox_dir)),
                "start_time": time.time()
            }
            self.host_os.set_daemons_registry(registry)
            
            system_logger.info(f"[Host OS] Запущен фоновый демон '{name}' (PID: {pid})")
            return SkillResult.ok(
                f"Демон '{name}' успешно запущен (PID: {pid}).\n"
                f"Логи перенаправлены в файл: sandbox/{log_path.name}\n"
                f"Вы можете отслеживать его статус в контексте Host OS (Active Daemons) или остановить с помощью stop_daemon."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при запуске демона: {e}")

    @skill()
    async def stop_daemon(self, pid: int) -> SkillResult:
        """Останавливает работающий фоновый демон по его PID."""
        if self.host_os.access_level < HostOSAccessLevel.OBSERVER:
            return SkillResult.fail("Отказано в доступе.")

        try:
            registry = self.host_os.get_daemons_registry()
            pid_str = str(pid)
            
            if pid_str not in registry:
                return SkillResult.fail(f"Ошибка: Демон с PID {pid} не найден в реестре.")
                
            name = registry[pid_str]["name"]

            # Убиваем процесс
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                proc.wait(timeout=3)
            except psutil.NoSuchProcess:
                pass  # Уже мертв
            except psutil.TimeoutExpired:
                proc.kill()
            except Exception as e:
                return SkillResult.fail(f"Не удалось завершить процесс: {e}")

            # Удаляем из реестра
            del registry[pid_str]
            self.host_os.set_daemons_registry(registry)
            
            system_logger.info(f"[Host OS] Остановлен фоновый демон '{name}' (PID: {pid})")
            return SkillResult.ok(f"Демон '{name}' (PID: {pid}) успешно остановлен вручную.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при остановке демона: {e}")
        
    @skill()
    async def execute_sandbox_func(
        self, filepath: str, func_name: str, kwargs: dict = None
    ) -> SkillResult:
        """
        Универсальный шлюз для безопасного вызова конкретной функции или корутины из Python-скрипта в песочнице.
        Позволяет передать аргументы и напрямую получить возвращаемый результат (return), минуя создание одноразовых файлов.
        - filepath: путь к скрипту (например, 'sandbox/directory/api.py')
        - func_name: имя функции для вызова (например, 'create_comment')
        - kwargs: словарь аргументов, которые будут переданы в функцию.
        """

        if kwargs is None:
            kwargs = {}

        timeout = self.host_os.config.execution_timeout_sec

        if self.host_os.access_level < HostOSAccessLevel.OBSERVER:
            return SkillResult.fail("Отказано в доступе.")

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file() or safe_path.suffix.lower() != ".py":
                return SkillResult.fail(
                    f"Ошибка: Файл не найден или это не .py скрипт ({safe_path.name})."
                )

            # Создаем временную директорию для оберток, чтобы не мусорить
            tmp_dir = self.host_os.sandbox_dir / ".tmp"
            tmp_dir.mkdir(exist_ok=True)

            wrapper_id = str(uuid.uuid4())[:8]
            wrapper_path = tmp_dir / f"rpc_wrapper_{wrapper_id}.py"

            # Невидимый скрипт-обертка:
            # 1. Забирает kwargs из stdin (чтобы избежать экранирования в строке)
            # 2. Динамически импортирует целевой файл
            # 3. Выполняет функцию (поддерживает async/await)
            # 4. Принтит результат в JSON с уникальным маркером
            wrapper_code = """\
import sys
import json
import asyncio
import traceback
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

# Обеспечиваем корректные импорты для целевого скрипта
target_filepath = sys.argv[1]
func_name = sys.argv[2]
target_dir = str(Path(target_filepath).parent)
if target_dir not in sys.path:
    sys.path.insert(0, target_dir)

async def _runner(func, kwargs):
    if asyncio.iscoroutinefunction(func):
        return await func(**kwargs)
    return func(**kwargs)

def main():
    try:
        input_data = sys.stdin.read()
        kwargs = json.loads(input_data) if input_data.strip() else {}

        spec = spec_from_file_location("dynamic_sandbox_module", target_filepath)
        if spec is None or spec.loader is None:
            raise ImportError(f"Не удалось загрузить модуль {target_filepath}")
            
        module = module_from_spec(spec)
        sys.modules["dynamic_sandbox_module"] = module
        spec.loader.exec_module(module)

        if not hasattr(module, func_name):
            raise AttributeError(f"В модуле {target_filepath} нет функции '{func_name}'")

        func = getattr(module, func_name)
        result = asyncio.run(_runner(func, kwargs))
        
        # Кастомный принт, чтобы отличить наш JSON от принтов самого скрипта
        sys.stdout.write("\\n---JAWL_RPC_RESULT---\\n")
        sys.stdout.write(json.dumps({"status": "ok", "result": result}, ensure_ascii=False) + "\\n")

    except Exception as e:
        sys.stdout.write("\\n---JAWL_RPC_RESULT---\\n")
        sys.stdout.write(json.dumps({
            "status": "error", 
            "error": str(e), 
            "traceback": traceback.format_exc()
        }, ensure_ascii=False) + "\\n")

if __name__ == "__main__":
    main()
"""
            wrapper_path.write_text(wrapper_code, encoding="utf-8")

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(wrapper_path),
                str(safe_path),
                func_name,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.host_os.sandbox_dir),
            )

            stdin_data = json.dumps(kwargs, ensure_ascii=False).encode("utf-8")

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=stdin_data), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                wrapper_path.unlink(missing_ok=True)
                return SkillResult.fail(
                    f"Функция работала дольше {timeout} секунд и была убита (Таймаут)."
                )

            # Чистим временный файл-обертку
            wrapper_path.unlink(missing_ok=True)

            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()

            rpc_prefix = "---JAWL_RPC_RESULT---"
            if rpc_prefix in out_str:
                parts = out_str.split(rpc_prefix)
                script_stdout = parts[0].strip()  # Вывод, который функция сделала через print()
                rpc_json_str = parts[1].strip()

                try:
                    rpc_result = json.loads(rpc_json_str)
                except json.JSONDecodeError:
                    return SkillResult.fail(
                        f"Скрипт отработал, но результат невалиден.\nSTDOUT:\n{out_str}\nSTDERR:\n{err_str}"
                    )

                report =[]
                if script_stdout:
                    report.append(
                        f"STDOUT скрипта:\n```\n{truncate_text(script_stdout, 2000)}\n```"
                    )
                if err_str:
                    report.append(
                        f"STDERR скрипта:\n```\n{truncate_text(err_str, 2000)}\n```"
                    )

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
                # Если RPC-маркер не найден, значит функция упала с фатальной ошибкой (например, syntax error)
                return SkillResult.fail(
                    f"Скрипт завершился с ошибкой (код {process.returncode}).\n"
                    f"STDOUT:\n{truncate_text(out_str, 2000)}\n"
                    f"STDERR:\n{truncate_text(err_str, 2000)}"
                )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        
        except Exception as e:
            return SkillResult.fail(f"Внутренняя ошибка RPC: {e}")
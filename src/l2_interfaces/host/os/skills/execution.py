import asyncio
import sys
import psutil

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
            log_path = self.host_os.sandbox_dir / f"daemon_{safe_name}.log"
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
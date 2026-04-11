import asyncio
import sys
import psutil
from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient, MadnessLevel

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSExecution:
    """
    Навыки агента для запуска кода и управления процессами.
    Самый опасный модуль: строго контролируется через Madness Level.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    def _truncate_output(self, text: str) -> str:
        """Обрезает вывод, чтобы огромный лог из консоли не взорвал контекст агента."""

        max_chars = 5000

        if len(text) > max_chars:
            return (
                text[:max_chars]
                + f"\n... [Вывод обрезан. Превышен лимит в {max_chars} символов] ..."
            )

        return text

    @skill()
    async def execute_script(self, filepath: str) -> SkillResult:
        """
        Запускает скрипт (.py, .sh, .bat, .js).
        По умолчанию (при madness_level = 1) запускает только из папки sandbox/.
        Автоматически завершается, если работает дольше timeout секунд.
        """

        timeout = self.host_os.config.execution_timeout_sec

        if self.host_os.madness_level < MadnessLevel.VOYEUR: 
            return SkillResult.fail(
                "Отказано в доступе: выполнение скриптов разрешено при madness_level >= 1."
            )

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            # Дополнительная проверка: Voyeur может запускать только внутри песочницы
            if (
                self.host_os.madness_level < MadnessLevel.SURGEON
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
                cmd = ["bash", str(safe_path)]

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
                return SkillResult.fail(
                    f"Скрипт работал дольше {timeout} секунд и был принудительно убит (Таймаут)."
                )

            stdout_str = self._truncate_output(
                stdout.decode("utf-8", errors="replace").strip()
            )
            stderr_str = self._truncate_output(
                stderr.decode("utf-8", errors="replace").strip()
            )

            exit_code = process.returncode
            system_logger.info(
                f"Выполнен скрипт {safe_path.name} (Код: {exit_code})"
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
        Доступно только при madness_level >= 2.
        """

        timeout = self.host_os.config.execution_timeout_sec

        if self.host_os.madness_level < MadnessLevel.SURGEON:
            return SkillResult.fail(
                "Отказано в доступе: выполнение shell-команд требует madness_level >= 2 (SURGEON)."
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
                return SkillResult.fail(
                    f"Команда работала дольше {timeout} секунд и была убита (Таймаут)."
                )

            stdout_str = self._truncate_output(
                stdout.decode("utf-8", errors="replace").strip()
            )
            stderr_str = self._truncate_output(
                stderr.decode("utf-8", errors="replace").strip()
            )

            exit_code = process.returncode
            system_logger.info(f"Выполнена shell-команда (Код: {exit_code})")

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
        Доступно только при madness_level >= 2.
        """

        if self.host_os.madness_level < MadnessLevel.SURGEON:
            return SkillResult.fail(
                "Отказано в доступе: управление процессами ОС требует madness_level >= 2 (SURGEON)."
            )

        try:
            process = psutil.Process(pid)
            process_name = process.name()

            process.terminate()
            process.wait(timeout=3)  # Даем 3 секунды на корректное завершение

            system_logger.info(f"Убит процесс {pid} ({process_name})")
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

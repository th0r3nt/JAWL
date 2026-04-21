import sys
import os
import shutil
import time
import subprocess
from pathlib import Path
import psutil
import questionary
from src.utils._tools import get_pid_file_path

from src.cli.widgets.ui import print_success, print_error, print_info, wait_for_enter

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PID_FILE = ROOT_DIR / "src" / "utils" / "local" / "data" / "agent.pid"
ENV_FILE = ROOT_DIR / ".env"
ENV_EXAMPLE = ROOT_DIR / ".env.example"
MAIN_SCRIPT = ROOT_DIR / "src" / "main.py"
STOP_FILE = ROOT_DIR / "src" / "utils" / "local" / "data" / "agent.stop"


def _is_agent_running() -> bool:
    """Проверяет, работает ли агент на самом деле."""
    pid_file = get_pid_file_path()
    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())
        if psutil.pid_exists(pid):
            # Дополнительная проверка: это всё еще Python-процесс?
            proc = psutil.Process(pid)
            return proc.is_running() and "python" in proc.name().lower()
        return False
    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
        # Если файл есть, а процесса нет - файл мусорный, удаляем
        if pid_file.exists():
            pid_file.unlink()
        return False


def _check_and_setup_env() -> bool:
    """
    Проверяет наличие файла .env и базовых ключей.
    Если ключей нет - просит пользователя ввести их прямо в CLI.
    """

    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            shutil.copy(ENV_EXAMPLE, ENV_FILE)
            print_info("Создан базовый файл .env из .env.example")
        else:
            print_error("Не найден ни .env, ни .env.example.")
            return False

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        env_content = f.readlines()

    # Проверяем, заполнен ли LLM_API_KEY_1
    key_found = False
    for line in env_content:
        if line.startswith("LLM_API_KEY_1=") and len(line.strip()) > 10:
            key_found = True
            break

    if not key_found:
        print_info("Похоже, вы еще не добавили API-ключ для LLM.")
        api_key = questionary.text(
            "Введите ваш LLM API Key (или нажмите Enter для отмены):"
        ).ask()

        if not api_key:
            print_error("Запуск отменен: API ключ обязателен для работы агента.")
            return False

        # Перезаписываем .env с новым ключом
        new_content = []
        for line in env_content:
            if line.startswith("LLM_API_KEY_1="):
                new_content.append(f'LLM_API_KEY_1="{api_key}"\n')
            else:
                new_content.append(line)

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_content)

        print_success("API ключ успешно сохранен в .env")

    return True


def start_agent_screen() -> None:
    """Экран запуска агента."""

    if _is_agent_running():
        print_error("Агент уже запущен. Если он завис, сначала остановите его.")
        wait_for_enter()
        return

    if not _check_and_setup_env():
        wait_for_enter()
        return

    print_info(" Инициализация систем агента.")
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    logs_dir = ROOT_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    crash_log_path = logs_dir / "crash.log"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)
    # Жестко указываем Python выводить ошибки в UTF-8, чтобы избежать крякозябр
    env["PYTHONIOENCODING"] = "utf-8"

    # Изолируем процесс агента от терминала, чтобы Ctrl+C в логах не убивал его
    kwargs = {}
    if os.name == "nt":
        # Windows: создаем новую группу процессов
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # Linux/Mac: создаем новую сессию
        kwargs["start_new_session"] = True

    try:
        with open(crash_log_path, "a", encoding="utf-8") as crash_log:
            process = subprocess.Popen(
                [sys.executable, str(MAIN_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=crash_log,
                cwd=str(ROOT_DIR),
                env=env,
                **kwargs,  # <-- Распаковываем аргументы изоляции
            )

        PID_FILE.write_text(str(process.pid))

        print_success("Агент успешно запущен в фоновом режиме.")
        print_info(
            " Для просмотра того, что он делает, выберите 'Открыть логи' в главном меню."
        )

    except Exception as e:
        print_error(f"Не удалось запустить агента: {e}")

    wait_for_enter()


def stop_agent_screen() -> None:
    """Экран остановки агента."""

    if not _is_agent_running():
        print_info(" Агент в данный момент не запущен.")
        if PID_FILE.exists():
            PID_FILE.unlink()
        wait_for_enter()
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        process = psutil.Process(pid)

        print_info(" Отправка сигнала на плавное завершение (Graceful Shutdown)...")
        # Создаем флаг-файл, агент его увидит и начнет сворачиваться
        STOP_FILE.touch(exist_ok=True)

        # Ждем до 5 секунд, пока агент корректно закроет БД и завершится
        timeout = 5
        is_dead = False

        for _ in range(timeout):
            if not process.is_running():
                is_dead = True
                break
            time.sleep(1)

        if is_dead:
            print_success("Агент успешно и безопасно остановлен.")
        else:
            print_error(
                f"Агент не ответил за {timeout} секунд. Принудительное убийство (SIGKILL)."
            )
            process.kill()
            print_success("Процесс агента выслежен и убит.")

        # Убираем за собой мусор
        if PID_FILE.exists():
            PID_FILE.unlink()
        if STOP_FILE.exists():
            STOP_FILE.unlink()

    except Exception as e:
        print_error(f"Ошибка при попытке остановить агента: {e}")

    wait_for_enter()

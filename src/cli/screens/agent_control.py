import sys
import os
import shutil
import time
import subprocess
from pathlib import Path
import psutil
import asyncio
from telethon import TelegramClient
from dotenv import dotenv_values
import questionary
from pydantic import ValidationError
from src.utils.settings import load_config
from src.utils._tools import get_pid_file_path

from src.cli.widgets.ui import print_success, print_error, print_info, wait_for_enter

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PID_FILE = ROOT_DIR / "src" / "utils" / "local" / "data" / "agent.pid"
ENV_FILE = ROOT_DIR / ".env"
ENV_EXAMPLE = ROOT_DIR / ".env.example"
MAIN_SCRIPT = ROOT_DIR / "src" / "main.py"
STOP_FILE = ROOT_DIR / "src" / "utils" / "local" / "data" / "agent.stop"
PROMPTS_DIR = ROOT_DIR / "src" / "l3_agent" / "prompt" / "personality"


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
            # Автовосстановление кодировки при копировании
            try:
                with open(ENV_EXAMPLE, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(ENV_EXAMPLE, "r", encoding="cp1251") as f:
                    content = f.read()

            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            print_info(" Создан базовый файл .env из .env.example")
        else:
            print_error("Не найден ни .env, ни .env.example.")
            return False

    # Магия защиты от блокнота Windows
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            env_content = f.readlines()
    except UnicodeDecodeError:
        # Юзер сохранил файл в ANSI. Читаем и сразу лечим, перезаписывая в UTF-8
        with open(ENV_FILE, "r", encoding="cp1251") as f:
            env_content = f.readlines()
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(env_content)

    # Проверяем, заполнен ли LLM_API_KEY_1
    key_found = False
    for line in env_content:
        if line.startswith("LLM_API_KEY_1=") and len(line.strip()) > 14:
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


def _check_and_setup_prompts() -> None:
    """Проверяет наличие файлов промпта личности. Если их нет, создает из .example.md"""
    if not PROMPTS_DIR.exists():
        return

    created_any = False

    for example_file in PROMPTS_DIR.rglob("*.example.md"):
        # Формируем имя без .example (например: SOUL.example.md -> SOUL.md)
        target_name = example_file.name.replace(".example.md", ".md")
        target_file = example_file.with_name(target_name)

        if not target_file.exists():
            shutil.copy(example_file, target_file)
            print_info(f" Создан базовый файл личности: {target_name}")
            created_any = True

    if created_any:
        print_info(
            " Напоминание: вы можете полностью кастомизировать характер агента, редактируя эти файлы "
            "или добавляя любые новые .md документы в папку src/l3_agent/prompt/personality/"
        )


def _validate_configs() -> bool:
    """Предполетная проверка конфигураций. Отлавливает ошибки до старта процесса."""

    try:
        load_config()
        return True

    except ValidationError as e:
        print_error("Ошибка структуры конфигурации (yaml не совпадает со схемой):")
        for err in e.errors():
            loc = " -> ".join(map(str, err.get("loc", [])))
            print_info(f"[{loc}]: {err.get('msg')}")

        return False

    except Exception as e:
        print_error(f"Критическая ошибка при чтении настроек: {e}")
        return False


def _telethon_auth_flow() -> bool:
    """Предполетная авторизация сессии Telethon, если она включена в конфиге."""

    settings, interfaces = load_config()

    # Если интерфейс отключен, просто идем дальше
    if not interfaces.telegram.telethon.enabled:
        return True

    env_dict = dotenv_values(ENV_FILE)
    api_id = env_dict.get("TELETHON_API_ID")
    api_hash = env_dict.get("TELETHON_API_HASH")

    # Если ключей нет в .env - просим ввести
    if not api_id or not api_hash:
        print_info(
            " Для работы Telethon требуются API_ID и API_HASH (можно получить на my.telegram.org)."
        )

        api_id_input = questionary.text("Введите TELETHON_API_ID:").ask()
        if not api_id_input:
            print_error("Запуск отменен: TELETHON_API_ID обязателен.")
            return False

        api_hash_input = questionary.text("Введите TELETHON_API_HASH:").ask()
        if not api_hash_input:
            print_error("Запуск отменен: TELETHON_API_HASH обязателен.")
            return False

        # Сохраняем введенные данные в .env
        with open(ENV_FILE, "a", encoding="utf-8") as f:
            f.write(f'\nTELETHON_API_ID="{api_id_input.strip()}"\n')
            f.write(f'TELETHON_API_HASH="{api_hash_input.strip()}"\n')

        api_id = api_id_input.strip()
        api_hash = api_hash_input.strip()

    # Путь к сессии
    session_name = interfaces.telegram.telethon.session_name
    session_dir = ROOT_DIR / "src" / "utils" / "local" / "data" / "telethon"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / session_name

    # Асинхронная обертка для мини-клиента
    async def _auth() -> bool:
        try:
            clean_api_id = int(api_id) if str(api_id).isdigit() else api_id
            client = TelegramClient(str(session_path), clean_api_id, api_hash)

            await client.connect()
            if not await client.is_user_authorized():
                print_info(" Сессия Telegram не найдена. Потребуется авторизация.")
                # Вызываем встроенный механизм Telethon. Он сам спросит телефон, СМС и 2FA пароль в консоли
                await client.start()

            me = await client.get_me()
            name = me.first_name or "Unknown"
            if getattr(me, "last_name", None):
                name += f" {me.last_name}"

            print_success(f"Telegram сессия активна (Пользователь: {name}).")
            await client.disconnect()
            return True

        except Exception as e:
            print_error(f"Ошибка при авторизации Telethon: {e}")
            return False

    # Запускаем асинхронный флоу авторизации в синхронном CLI
    print_info(" Проверка сессии Telegram (Telethon)...")
    return asyncio.run(_auth())


def start_agent_screen() -> None:
    """Экран запуска агента."""

    if _is_agent_running():
        print_error("Агент уже запущен. Если он завис, сначала остановите его.")
        wait_for_enter()
        return

    # Предполетная проверка
    if not _validate_configs():
        wait_for_enter()
        return

    _check_and_setup_prompts()

    if not _check_and_setup_env():
        wait_for_enter()
        return

    # Интерактивная авторизация Telethon (если включен)
    if not _telethon_auth_flow():
        wait_for_enter()
        return

    print_info(" Инициализация систем агента.")
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    logs_dir = ROOT_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    agent_log_path = logs_dir / "agent.log"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)
    env["PYTHONIOENCODING"] = "utf-8"

    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    try:
        # Открываем лог-файл для перехвата крашей (stderr=subprocess.STDOUT)
        with open(agent_log_path, "a", encoding="utf-8") as agent_log:
            process = subprocess.Popen(
                [sys.executable, str(MAIN_SCRIPT)],
                stdout=agent_log,
                stderr=subprocess.STDOUT,
                cwd=str(ROOT_DIR),
                env=env,
                **kwargs,
            )

        PID_FILE.write_text(str(process.pid))

        # Health Check (проверка пульса)
        time.sleep(3)  # Даем время на краш (ошибки импорта или синтаксиса)

        if process.poll() is not None:
            # Процесс умер
            if PID_FILE.exists():
                PID_FILE.unlink()

            print_error("Агент завершился с ошибкой сразу после старта.")
            try:
                with open(agent_log_path, "r", encoding="utf-8") as f:
                    tail = "".join(f.readlines()[-15:]).strip()
                    if tail:
                        print_info(f"Последние логи (logs/agent.log):\n{tail}")
            except Exception:
                pass

            wait_for_enter()
            return

        print_success("Агент успешно запущен в фоновом режиме.")
        time.sleep(1)
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

        print_info(" Отправка сигнала на плавное завершение (Graceful Shutdown).")
        # Создаем флаг-файл, агент его увидит и начнет сворачиваться
        STOP_FILE.touch(exist_ok=True)

        # Ждем до 15 секунд, пока агент корректно закроет БД и завершится
        timeout = 15
        is_dead = False

        for _ in range(timeout):
            if not process.is_running():
                is_dead = True
                break
            time.sleep(1)

        if is_dead:
            print_success("Агент успешно остановлен.")
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

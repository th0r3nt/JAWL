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


def _check_and_setup_env() -> tuple[bool, bool]:
    """
    Проверяет наличие файла .env и базовых ключей.
    Обеспечивает авто-настройку для локальных LLM (Ollama/vLLM) без лишних вопросов.
    Возвращает: (Успех_проверки, Были_ли_созданы_или_изменены_файлы)
    """

    was_modified = False

    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            try:
                with open(ENV_EXAMPLE, "r", encoding="utf-8-sig") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(ENV_EXAMPLE, "r", encoding="cp1251") as f:
                    content = f.read()

            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            print_info(" Создан базовый файл .env из .env.example")
            was_modified = True
        else:
            print_error("Не найден ни .env, ни .env.example.")
            return False, False

    try:
        with open(ENV_FILE, "r", encoding="utf-8-sig") as f:
            env_content = f.readlines()

    except UnicodeDecodeError:
        with open(ENV_FILE, "r", encoding="cp1251") as f:
            env_content = f.readlines()

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(env_content)

    key_found = False
    local_url_found = False

    for line in env_content:
        line_stripped = line.strip()
        # Ищем любой ключ, начинающийся на LLM_API_KEY_
        if line_stripped.startswith("LLM_API_KEY_") and "=" in line_stripped:
            val = line_stripped.split("=", 1)[1].strip("\"' ")
            if len(val) > 0:
                key_found = True
        # Ищем, не указал ли юзер локальный URL
        elif line_stripped.startswith("LLM_API_URL=") and "=" in line_stripped:
            val = line_stripped.split("=", 1)[1].strip("\"' ").lower()
            if "localhost" in val or "127.0.0.1" in val or "0.0.0.0" in val:
                local_url_found = True

    if not key_found:
        if local_url_found:
            # Автоматически добавляем заглушку без лишних вопросов
            new_content = []
            for line in env_content:
                if line.startswith("LLM_API_KEY_1="):
                    new_content.append('LLM_API_KEY_1="local_dummy_key"\n')
                else:
                    new_content.append(line)
            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.writelines(new_content)
            print_info(
                " Обнаружен локальный URL без ключа. Добавлена заглушка 'local_dummy_key'."
            )
            was_modified = True
        else:
            print_info(" Похоже, вы еще не настроили подключение к LLM.")
            api_url = questionary.text(
                "Введите Base URL для LLM (например, ссылку для Gemini или локальной модели).\nОставьте пустым для стандартного OpenAI API:"
            ).ask()

            if api_url is None:
                return False, False

            is_local = False
            if api_url:
                url_lower = api_url.lower()
                if (
                    "localhost" in url_lower
                    or "127.0.0.1" in url_lower
                    or "0.0.0.0" in url_lower
                ):
                    is_local = True

            api_key = questionary.text(
                "Введите ваш LLM API Key (Обязательно для облачных моделей, для локальных - пропустить):"
            ).ask()

            if not api_key:
                if is_local:
                    api_key = "local_dummy_key"
                    print_info(
                        " API ключ не указан, но обнаружен локальный URL."
                    )
                else:
                    print_error(
                        "Запуск отменен: API ключ обязателен для работы агента (если модель не локальная)."
                    )
                    return False, False

            new_content = []
            for line in env_content:
                if line.startswith("LLM_API_KEY_1="):
                    new_content.append(f'LLM_API_KEY_1="{api_key.strip()}"\n')
                elif line.startswith("LLM_API_URL="):
                    new_content.append(f'LLM_API_URL="{api_url.strip()}"\n')
                else:
                    new_content.append(line)

            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.writelines(new_content)

            print_success("\nНастройки LLM успешно сохранены в .env")
            was_modified = True

    return True, was_modified


def _check_and_setup_prompts() -> bool:
    """Проверяет наличие файлов промпта личности. Если их нет, создает из .example.md."""
    if not PROMPTS_DIR.exists():
        PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    created_any = False

    for example_file in PROMPTS_DIR.rglob("*.example.md"):
        target_name = example_file.name.replace(".example.md", ".md")
        target_file = example_file.with_name(target_name)

        if not target_file.exists():
            shutil.copy(example_file, target_file)
            print_info(f" Создан базовый файл личности: {target_name}")
            created_any = True

    return created_any


def _validate_configs() -> bool:
    """Предполетная проверка конфигураций."""
    try:
        load_config()
        return True

    except ValidationError as e:
        print_error("Ошибка структуры конфигурации (yaml не совпадает со схемой):")
        for err in e.errors():
            loc = " -> ".join(map(str, err.get("loc", [])))
            print_info(f"[{loc}]: {err.get('msg')}")

        print_info(
            "\n 💡 Подсказка: если вы обновили JAWL, удалите старые файлы settings.yaml и interfaces.yaml в папке config/, чтобы система пересоздала их из актуальных шаблонов."
        )
        return False

    except Exception as e:
        print_error(f"Критическая ошибка при чтении настроек: {e}")
        return False


def _telethon_auth_flow() -> bool:
    """Предполетная авторизация сессии Telethon, если она включена в конфиге."""
    settings, interfaces = load_config()

    if not interfaces.telegram.telethon.enabled:
        return True

    env_dict = dotenv_values(ENV_FILE, encoding="utf-8-sig")
    api_id = env_dict.get("TELETHON_API_ID")
    api_hash = env_dict.get("TELETHON_API_HASH")

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

        with open(ENV_FILE, "a", encoding="utf-8") as f:
            f.write(f'\nTELETHON_API_ID="{api_id_input.strip()}"\n')
            f.write(f'TELETHON_API_HASH="{api_hash_input.strip()}"\n')

        api_id = api_id_input.strip()
        api_hash = api_hash_input.strip()

    session_name = interfaces.telegram.telethon.session_name
    session_dir = (
        ROOT_DIR / "src" / "utils" / "local" / "data" / "interfaces" / "telegram" / "telethon"
    )
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / session_name

    async def _auth() -> bool:
        try:
            clean_api_id = int(api_id) if str(api_id).isdigit() else api_id
            client = TelegramClient(str(session_path), clean_api_id, api_hash)

            await client.connect()
            if not await client.is_user_authorized():
                print_info(" Сессия Telegram не найдена. Потребуется авторизация.")
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

    print_info(" Проверка сессии Telegram (Telethon)...")
    return asyncio.run(_auth())


def start_agent_screen() -> None:
    """Экран запуска агента."""
    if _is_agent_running():
        print_error("Агент уже запущен. Если он завис, сначала остановите его.")
        wait_for_enter()
        return

    settings_existed = (ROOT_DIR / "config" / "settings.yaml").exists()
    interfaces_existed = (ROOT_DIR / "config" / "interfaces.yaml").exists()

    if not _validate_configs():
        wait_for_enter()
        return

    configs_created = not (settings_existed and interfaces_existed)
    prompts_created = _check_and_setup_prompts()

    env_success, env_modified = _check_and_setup_env()
    if not env_success:
        wait_for_enter()
        return

    if configs_created or prompts_created or env_modified:
        print("\n")
        print_info(" [Первичная инициализация завершена]")
        print("\n")
        print_info(" Были созданы базовые файлы конфигурации.")
        print_info(
            " Обязательно зайдите в config/interfaces.yaml и настройте под себя возможности агента."
        )
        print_info(" По умолчанию большинство интерфейсов отключено в целях безопасности.")
        print_info(
            " Также проверьте config/settings.yaml для настройки параметров модели, БД и лимитов."
        )
        print("\n")
        print_info(" Были созданы файлы личности агента и/или .env.")
        print_info(
            " Просмотрите src/l3_agent/prompt/personality/, чтобы настроить личность и характер агента."
        )
        print_success("\nПосле финальной настройки выберите 'Запустить агента' в меню еще раз.")
        wait_for_enter()
        return

    if not _telethon_auth_flow():
        wait_for_enter()
        return

    print_info(" Инициализация систем агента.")
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)
    env["PYTHONIOENCODING"] = "utf-8"

    # Гарантируем полное отсоединение от родительского процесса и консоли
    kwargs = {"close_fds": True}
    if os.name == "nt":
        # 0x08000000 = DETACHED_PROCESS - изолирует процесс от родительской консоли
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
    else:
        kwargs["start_new_session"] = True

    crash_log_path = ROOT_DIR / "logs" / "startup" / "startup_error.log"
    crash_log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Открываем реальный файл для логгирования фатальных крашей, избегая блокировок tempfile
        f_err = open(crash_log_path, "w", encoding="utf-8")

        try:
            process = subprocess.Popen(
                [sys.executable, str(MAIN_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=f_err,
                cwd=str(ROOT_DIR),
                env=env,
                **kwargs,
            )
            PID_FILE.write_text(str(process.pid))

        finally:
            # Родительский процесс закрывает свой хэндл, дочерний продолжает писать
            f_err.close()

        # Даем агенту 5 секунд на старт
        time.sleep(5)

        # Проверяем, не упал ли он
        if process.poll() is not None:
            if PID_FILE.exists():
                PID_FILE.unlink()
            print_error("Агент завершился с ошибкой сразу после старта.")

            error_output = crash_log_path.read_text(encoding="utf-8", errors="replace").strip()

            if error_output:
                print_info("Детали критической ошибки (Traceback):")
                print(f"\n{error_output}\n")
            else:
                print_info("Проверьте основной лог (logs/system.log) для получения деталей.")

            wait_for_enter()
            return

        print_success("Агент успешно запущен в фоновом режиме.")
        time.sleep(1)
        print_info(" Для просмотра логов выберите 'Логи' в главном меню.")

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
        STOP_FILE.touch(exist_ok=True)

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

        if PID_FILE.exists():
            PID_FILE.unlink()
        if STOP_FILE.exists():
            STOP_FILE.unlink()

    except Exception as e:
        print_error(f"Ошибка при попытке остановить агента: {e}")

    wait_for_enter()

import os
import time
import asyncio
import traceback
from dotenv import load_dotenv

from src.utils._tools import get_pid_file_path, get_lock_file_path, SystemInstanceLock
from src.utils.logger import main_logger, apply_logger_config
from src.utils.event.bus import EventBus
from src.utils.settings import load_config
from src.l3_agent.skills.registry import clear_registry
from src import __version__

# Архитектурная триада
from src.system.container import SystemContainer
from src.builder import SystemBuilder
from src.system.orchestrator import SystemOrchestrator


async def main() -> int:
    """
    Асинхронная точка входа в систему.
    Загружает конфигурацию, собирает DI-контейнер через Билдер,
    и передает его в Оркестратор для запуска.
    Возвращает код завершения (0 - выключение, 1 - перезагрузка).
    """

    load_dotenv(override=True)
    clear_registry()

    event_bus = EventBus()
    settings, interfaces = load_config()

    apply_logger_config(
        max_size_mb=settings.system.logging.max_file_size_mb,
        backup_count=settings.system.logging.backup_count,
    )

    pid_file = get_pid_file_path()
    lock_file = get_lock_file_path()

    instance_lock = SystemInstanceLock(lock_file)
    if not instance_lock.acquire():
        # Если блокировку получить не удалось, значит агент уже работает
        print("\n[!] Критическая ошибка: Экземпляр агента уже запущен.")
        print(f"[!] Файл блокировки ({lock_file.name}) заблокирован операционной системой.")
        print(
            "[!] Если вы уверены, что это сбой, закройте скрытые процессы python.exe вручную.\n"
        )
        return 0

    # Создаем обычный (незаблокированный) PID-файл для чтения из CLI
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    main_logger.info(f"[System] Инициализация JAWL v{__version__} (PID: {os.getpid()}).")

    orchestrator = None

    try:
        # 1. Глобальный прокси
        PROXY_URL = os.getenv("PROXY_URL", "").strip()
        if PROXY_URL:
            os.environ["HTTP_PROXY"] = PROXY_URL
            os.environ["HTTPS_PROXY"] = PROXY_URL
            os.environ["http_proxy"] = PROXY_URL
            os.environ["https_proxy"] = PROXY_URL
            os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
            os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
            main_logger.info("[System] Глобальный прокси активирован.")

        # 2. Ключи LLM
        LLM_API_URL = os.getenv("LLM_API_URL", "")
        LLM_API_KEYS = [
            v
            for k, v in sorted(os.environ.items())
            if k.startswith("LLM_API_KEY_") and v.strip()
        ] or ["local_dummy_key"]
        SUB_LLM_API_URL = os.getenv("SUB_LLM_API_URL", "")
        SUB_LLM_API_KEYS = [
            v
            for k, v in sorted(os.environ.items())
            if k.startswith("SUB_LLM_API_KEY_") and v.strip()
        ]

        # 3. Секреты для L2 и L3
        env_vars = {
            "LLM_API_URL": LLM_API_URL,
            "LLM_API_KEYS": LLM_API_KEYS,
            "SUB_LLM_API_URL": SUB_LLM_API_URL,
            "SUB_LLM_API_KEYS": SUB_LLM_API_KEYS,
            "PROXY_URL": PROXY_URL,
            "TELETHON_API_ID": os.getenv("TELETHON_API_ID"),
            "TELETHON_API_HASH": os.getenv("TELETHON_API_HASH"),
            "AIOGRAM_BOT_TOKEN": os.getenv("AIOGRAM_BOT_TOKEN"),
            "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN"),
            "EMAIL_ACCOUNT": os.getenv("EMAIL_ACCOUNT"),
            "EMAIL_PASSWORD": os.getenv("EMAIL_PASSWORD"),
            "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
            "WEBHOOK_SECRET": os.getenv("WEBHOOK_SECRET"),
            "ELEVENLABS_API_KEY": os.getenv("ELEVENLABS_API_KEY"),
            "ELEVENLABS_API_URL": os.getenv(
                "ELEVENLABS_API_URL", "https://api.elevenlabs.io/v1"
            ),
            "CLOUD_WHISPER_API_KEY": os.getenv("CLOUD_WHISPER_API_KEY")
            or os.getenv("WHISPER_API_KEY")
            or os.getenv("OPENAI_API_KEY"),
            "CLOUD_WHISPER_API_URL": os.getenv("CLOUD_WHISPER_API_URL"),
        }

        # ==================================================================
        # Сборка системы
        
        container = SystemContainer(settings, interfaces, event_bus)
        builder = SystemBuilder(container)
        builder.with_l0_states()
        await builder.with_l1_databases()
        builder.with_l2_interfaces(env_vars)
        builder.with_l3_agent(env_vars)

        container = builder.build()

        # Передача управления Оркестратору
        orchestrator = SystemOrchestrator(container)
        exit_code = await orchestrator.run()
        return exit_code

    except asyncio.CancelledError:
        return 0

    except KeyboardInterrupt:
        main_logger.info("[System] Получен сигнал прерывания.")
        return 0

    except BaseException as e:
        main_logger.error(f"[System] Критическая ошибка: {type(e).__name__} - {e}")
        main_logger.error(traceback.format_exc())
        return 0

    finally:
        if orchestrator:
            await orchestrator.stop()

        # Снимаем блокировку, чтобы иметь возможность удалить файл на Windows
        instance_lock.release()

        # Ownership Check перед удалением файлов
        if pid_file.exists():
            try:
                current_pid = int(pid_file.read_text().strip())
                if current_pid == os.getpid():
                    pid_file.unlink(missing_ok=True)
                    lock_file.unlink(missing_ok=True)
                    main_logger.info("[System] PID-файлы удалены.")
                else:
                    main_logger.warning(
                        f"[System] PID-файл содержит чужой PID ({current_pid}). Удаление отменено."
                    )
            except Exception as e:
                main_logger.debug(f"[System] Ошибка при валидации/удалении PID-файла: {e}")
                try:
                    pid_file.unlink(missing_ok=True)
                    lock_file.unlink(missing_ok=True)
                except Exception:
                    pass


if __name__ == "__main__":
    while True:
        try:
            exit_code = asyncio.run(main())
            if exit_code == 1:
                main_logger.info("[System] Инициализирована перезагрузка.")
                time.sleep(1)
                continue
            else:
                break
        except KeyboardInterrupt:
            break

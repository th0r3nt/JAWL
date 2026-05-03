import os
import time
import asyncio
import traceback
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Any, TYPE_CHECKING

from src.utils._tools import get_pid_file_path
from src.utils.logger import system_logger, apply_logger_config
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import load_config, SettingsConfig, InterfacesConfig
from src.l3_agent.context.registry import ContextRegistry
from src.l3_agent.skills.registry import clear_registry
from src import __version__

# Архитектурные обертки
from src.builder import SystemBuilder # Фасад
from src.utils.event.bridge import EventBridge # Строитель

if TYPE_CHECKING:
    from src.l0_state.agent.state import AgentState
    from src.l2_interfaces.host.os.state import HostOSState
    from src.l2_interfaces.host.terminal.state import HostTerminalState
    from src.l2_interfaces.telegram.telethon.state import TelethonState
    from src.l2_interfaces.telegram.aiogram.state import AiogramState
    from src.l2_interfaces.github.state import GithubState
    from src.l2_interfaces.email.state import EmailState
    from src.l2_interfaces.web.search.state import WebSearchState
    from src.l2_interfaces.web.http.state import WebHTTPState
    from src.l2_interfaces.web.browser.state import WebBrowserState
    from src.l2_interfaces.web.hooks.state import WebHooksState
    from src.l2_interfaces.web.rss.state import WebRSSState
    from src.l2_interfaces.calendar.state import CalendarState
    from src.l2_interfaces.meta.state import CustomDashboardState

    from src.l1_databases.sql.manager import SQLManager
    from src.l1_databases.vector.manager import VectorManager
    from src.l1_databases.graph.manager import GraphManager

    from src.l3_agent.heartbeat import Heartbeat
    from src.l3_agent.llm.client import LLMClient


class System:
    """
    Корень композиции (Фасад).
    Хранит ссылки на все подсистемы и управляет жизненным циклом.
    Вся сложная инициализация инкапсулирована в SystemBuilder.
    """

    def __init__(
        self,
        event_bus: EventBus,
        settings_config: SettingsConfig,
        interfaces_config: InterfacesConfig,
    ):
        self.event_bus = event_bus
        self.settings = settings_config
        self.interfaces_config = interfaces_config

        self.root_dir = Path.cwd()
        self.local_data_dir = self.root_dir / "src" / "utils" / "local" / "data"

        # Хранилище компонентов, которые нужно запустить (например, поллинг Telethon)
        self._lifecycle_components: list[Any] = []

        # Возвращает в конце работы
        self._exit_code: int = 0  # 0 - выключение, 1 - перезагрузка

        # Заглушки L0 (Заполняются через SystemBuilder)
        self.agent_state: Optional["AgentState"] = None
        self.os_state: Optional["HostOSState"] = None
        self.terminal_state: Optional["HostTerminalState"] = None
        self.telethon_state: Optional["TelethonState"] = None
        self.aiogram_state: Optional["AiogramState"] = None
        self.github_state: Optional["GithubState"] = None
        self.email_state: Optional["EmailState"] = None
        self.web_search_state: Optional["WebSearchState"] = None
        self.web_http_state: Optional["WebHTTPState"] = None
        self.web_browser_state: Optional["WebBrowserState"] = None
        self.web_hooks_state: Optional["WebHooksState"] = None
        self.web_rss_state: Optional["WebRSSState"] = None
        self.calendar_state: Optional["CalendarState"] = None
        self.dashboard_state: Optional["CustomDashboardState"] = None

        # Заглушки L1-L3 (Заполняются через SystemBuilder)
        self.sql: Optional["SQLManager"] = None
        self.vector: Optional["VectorManager"] = None
        self.graph: Optional["GraphManager"] = None
        self.heartbeat: Optional["Heartbeat"] = None
        self.llm_client: Optional["LLMClient"] = None
        self.sub_llm_client: Optional["LLMClient"] = None

        self.context_registry = ContextRegistry()

    # ==========================================================
    # Изоляция сложной логики
    # ==========================================================

    def setup_l0_state(self):
        SystemBuilder(self).build_l0_state()

    async def setup_l1_databases(self):
        await SystemBuilder(self).build_l1_databases()

    def setup_l2_interfaces(
        self,
        # Telethon
        telethon_api_id: Optional[str] = None,
        telethon_api_hash: Optional[str] = None,
        aiogram_bot_token: Optional[str] = None,
        # GitHub
        github_token: Optional[str] = None,
        email_account: Optional[str] = None,
        email_password: Optional[str] = None,
        # Web Search
        tavily_api_key: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        """Читает конфиг, поднимает нужные интерфейсы и регистрирует их скиллы."""

        system_logger.info("[System] Инициализация L2 Interfaces.")

        env_vars = {
            # Telethon
            "TELETHON_API_ID": telethon_api_id,
            "TELETHON_API_HASH": telethon_api_hash,
            "AIOGRAM_BOT_TOKEN": aiogram_bot_token,
            # GitHub
            "GITHUB_TOKEN": github_token,
            "EMAIL_ACCOUNT": email_account,
            "EMAIL_PASSWORD": email_password,
            # Web Search
            "TAVILY_API_KEY": tavily_api_key,
            "WEBHOOK_SECRET": webhook_secret,
        }
        SystemBuilder(self).build_l2_interfaces(env_vars)

    def setup_l3_agent(
        self,
        llm_api_url: str,
        llm_api_keys: list[str],
        sub_llm_api_url: Optional[str] = None,
        sub_llm_api_keys: Optional[list[str]] = None,
    ):
        env_vars = {
            "LLM_API_URL": llm_api_url,
            "LLM_API_KEYS": llm_api_keys,
            "SUB_LLM_API_URL": sub_llm_api_url,
            "SUB_LLM_API_KEYS": sub_llm_api_keys,
        }
        SystemBuilder(self).build_l3_agent(env_vars)

    def _bridge_events_to_heartbeat(self):
        """Подписывает Heartbeat на все системные события через EventBridge."""
        EventBridge(self).setup_routing()

    # ===========================================
    # RUN & STOP
    # ===========================================

    async def run(
        self,
        # Main LLM
        llm_api_url: str,
        llm_api_keys: list[str],
        # Subagent LLM
        sub_llm_api_url: Optional[str] = None,
        sub_llm_api_keys: Optional[list[str]] = None,
        # Telethon
        telethon_api_id: Optional[str] = None,
        telethon_api_hash: Optional[str] = None,
        # Aiogram
        aiogram_bot_token: Optional[str] = None,
        # GitHub
        github_token: Optional[str] = None,
        # Email
        email_account: Optional[str] = None,
        email_password: Optional[str] = None,
        # Web Search
        tavily_api_key: Optional[str] = None,
        # Web Hooks
        webhook_secret: Optional[str] = None,
    ) -> int:
        """Запуск системы."""

        # Регистрация процесса
        pid_file = get_pid_file_path()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        system_logger.info(f"[System] Инициализация JAWL v{__version__} (PID: {os.getpid()}).")

        try:
            # Сборка архитектуры через методы-обертки (инкапсулируют SystemBuilder)
            self.setup_l0_state()
            await self.setup_l1_databases()

            # L2 INTERFACES
            self.setup_l2_interfaces(
                telethon_api_id=telethon_api_id,
                telethon_api_hash=telethon_api_hash,
                # Aiogram
                aiogram_bot_token=aiogram_bot_token,
                # GitHub
                github_token=github_token,
                email_account=email_account,
                email_password=email_password,
                # Web Search
                tavily_api_key=tavily_api_key,
                webhook_secret=webhook_secret,
            )

            # L3 AGENT
            self.setup_l3_agent(
                llm_api_url=llm_api_url,
                llm_api_keys=llm_api_keys,
                # Subagent LLM
                sub_llm_api_url=sub_llm_api_url,
                sub_llm_api_keys=sub_llm_api_keys,
            )

            self._bridge_events_to_heartbeat()

            # Запуск компонентов
            started_components = []
            for component in self._lifecycle_components:
                try:
                    await component.start()
                    started_components.append(component)
                except Exception as e:
                    system_logger.error(
                        f"[System] Ошибка запуска {component.__class__.__name__}: {e}"
                    )

            self._lifecycle_components = started_components

            system_logger.info(
                f"[System] JAWL успешно запущен. Имя агента: {self.settings.identity.agent_name}"
            )
            await self.event_bus.publish(Events.SYSTEM_CORE_START, status="online")

            # Запускаем фоновую следилку за файлом остановки
            stop_watcher_task = asyncio.create_task(self._watch_for_stop_file())

            # Точка входа в бесконечный цикл
            await self.heartbeat.start()  # Тут код заблокируется, пока агент работает

            # Если мы дошли сюда - агент остановился штатно
            stop_watcher_task.cancel()
            return self._exit_code

        finally:
            # Гарантированная очистка при любом исходе
            if pid_file.exists():
                pid_file.unlink()
                system_logger.info("[System] PID-файл удален.")

    async def _watch_for_stop_file(self):
        """Фоновая задача: ждет появления файла agent.stop от CLI для плавной остановки."""

        stop_file = self.local_data_dir / "agent.stop"

        # Очищаем старый файл, если он остался от прошлых крашей
        if stop_file.exists():
            try:
                stop_file.unlink()
            except Exception:
                pass

        try:
            while True:
                if stop_file.exists():
                    system_logger.info(
                        "[System] Получен сигнал от CLI (agent.stop). Запуск плавной остановки."
                    )
                    try:
                        stop_file.unlink()
                    except Exception:
                        pass

                    # Дергаем ту же ручку, как если бы агент сам решил выключиться
                    await self.event_bus.publish(
                        Events.SYSTEM_SHUTDOWN_REQUESTED,
                        reason="Остановка пользователем из меню",
                    )
                    break
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """
        Остановка и очистка ресурсов.
        """

        system_logger.info("[System] Инициирована остановка JAWL. Нанимаем киллеров, сколько убьем процесс.")
        await self.event_bus.publish(Events.SYSTEM_CORE_STOP, status="offline")

        if self.heartbeat:
            self.heartbeat.stop()

        for component in reversed(self._lifecycle_components):
            try:
                await component.stop()
            except Exception as e:
                system_logger.error(
                    f"[System] Ошибка при остановке {component.__class__.__name__}: {e}"
                )

        # Отрубаем всё к чертям
        if self.vector:
            await self.vector.disconnect()
        if self.sql:
            await self.sql.disconnect()
        if self.graph:
            await self.graph.disconnect()

        if self.event_bus:
            await self.event_bus.stop()
        if self.llm_client:
            await self.llm_client.close()

        # Закрываем сессии субагентов, только если это отдельный клиент
        if hasattr(self, "sub_llm_client") and self.sub_llm_client is not self.llm_client:
            await self.sub_llm_client.close()

        system_logger.info("[System] Остановка завершена. Процесс выслежен и жестоко убит.")


# ===================================================================
# ENTRY POINT
# ===================================================================


async def main() -> int:
    """
    Асинхронная точка входа в систему.
    Загружает конфигурацию, собирает DI-контейнер (System), поднимает базы данных,
    интерфейсы и запускает Heartbeat агента.
    Возвращает код завершения (0 - выключение, 1 - перезагрузка).
    """

    # Загружаем переменные окружения (override=True нужен, чтобы при ребуте подхватить изменения из .env)
    load_dotenv(override=True)

    # Очищаем глобальный кэш скиллов перед стартом, чтобы избежать дублирования при ребуте
    clear_registry()

    event_bus = EventBus()
    settings_config, interfaces_config = load_config()
    apply_logger_config(
        max_size_mb=settings_config.system.logging.max_file_size_mb,
        backup_count=settings_config.system.logging.backup_count,
    )

    system = System(
        event_bus=event_bus,
        settings_config=settings_config,
        interfaces_config=interfaces_config,
    )
    try:
        # Пробуем взять .env токены/API для интерфейсов
        # Telethon
        TELETHON_API_ID = os.getenv("TELETHON_API_ID", None)
        TELETHON_API_HASH = os.getenv("TELETHON_API_HASH", None)
        # Aiogram
        AIOGRAM_BOT_TOKEN = os.getenv("AIOGRAM_BOT_TOKEN", None)
        # GitHub
        GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)
        # Email
        EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT", None)
        EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", None)
        # Web Search
        TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", None)
        # Web Hooks
        WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", None)

        # Динамически собираем все ключи, которые начинаются с LLM_API_KEY_
        LLM_API_URL = os.getenv("LLM_API_URL", None)
        LLM_API_KEYS = [
            v
            for k, v in sorted(os.environ.items())
            if k.startswith("LLM_API_KEY_") and v.strip()
        ]

        # Фикс для локальных моделей: если URL указан, но ключей нет - ставим заглушку
        # Если юзер вообще ничего не ввел (и проигнорировал CLI), тоже ставим заглушку, чтобы ротатор не крашился
        if not LLM_API_KEYS:
            LLM_API_KEYS = ["local_dummy_key"]

        # Собираем ключи субагентов (если есть)
        SUB_LLM_API_URL = os.getenv("SUB_LLM_API_URL", None)
        SUB_LLM_API_KEYS = [
            v
            for k, v in sorted(os.environ.items())
            if k.startswith("SUB_LLM_API_KEY_") and v.strip()
        ]

        exit_code = await system.run(
            # Main LLM
            llm_api_url=LLM_API_URL,
            llm_api_keys=LLM_API_KEYS,
            # Subagents LLM
            sub_llm_api_url=SUB_LLM_API_URL,
            sub_llm_api_keys=SUB_LLM_API_KEYS,
            # Telethon
            telethon_api_id=TELETHON_API_ID,
            telethon_api_hash=TELETHON_API_HASH,
            # Aiogram
            aiogram_bot_token=AIOGRAM_BOT_TOKEN,
            # GitHub
            github_token=GITHUB_TOKEN,
            # Email
            email_account=EMAIL_ACCOUNT,
            email_password=EMAIL_PASSWORD,
            # Web Search
            tavily_api_key=TAVILY_API_KEY,
            # Web Hook
            webhook_secret=WEBHOOK_SECRET,
        )
        return exit_code

    except asyncio.CancelledError:
        return 0

    except KeyboardInterrupt:
        system_logger.info("[System] Получен сигнал прерывания.")
        return 0

    except BaseException as e:
        system_logger.error(f"[System] Критическая ошибка: {type(e).__name__} - {e}")
        system_logger.error(traceback.format_exc())
        return 0

    finally:
        await system.stop()


if __name__ == "__main__":
    while True:
        try:
            # Запускаем новый изолированный asyncio event loop
            exit_code = asyncio.run(main())

            if exit_code == 1:
                system_logger.info("[System] Инициализирована перезагрузка.")
                time.sleep(3)  # Даем ОС время на полное освобождение сокетов и дескрипторов
                continue
            else:
                break  # exit_code 0 -> штатное выключение

        except KeyboardInterrupt:
            break

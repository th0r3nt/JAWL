import os
import asyncio
import traceback
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# Утилиты
# ==========================================

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import load_config, SettingsConfig, InterfacesConfig
from src.utils.token_tracker import TokenTracker

# ==========================================
# L0 State
# ==========================================

from src.l0_state.agent.state import AgentState
from src.l0_state.interfaces.state import (
    HostOSState,
    HostTerminalState,
    TelethonState,
    AiogramState,
)

# ==========================================
# L1 Databases
# ==========================================

from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.sql.manager import SQLManager

# ==========================================
# L2 Interfaces
# ==========================================

# Host OS
from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.events import HostOSEvents
from src.l2_interfaces.host.os.skills.execution import HostOSExecution
from src.l2_interfaces.host.os.skills.files import HostOSFiles
from src.l2_interfaces.host.os.skills.network import HostOSNetwork
from src.l2_interfaces.host.os.skills.system import HostOSSystem

# Host Terminal
from src.l2_interfaces.host.terminal.client import HostTerminalClient
from src.l2_interfaces.host.terminal.events import HostTerminalEvents
from src.l2_interfaces.host.terminal.skills.messages import HostTerminalMessages

# Telethon
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.events import TelethonEvents
from src.l2_interfaces.telegram.telethon.skills.account import TelethonAccount
from src.l2_interfaces.telegram.telethon.skills.chats import TelethonChats
from src.l2_interfaces.telegram.telethon.skills.messages import TelethonMessages
from src.l2_interfaces.telegram.telethon.skills.moderation import TelethonModeration
from src.l2_interfaces.telegram.telethon.skills.polls import TelethonPolls
from src.l2_interfaces.telegram.telethon.skills.reactions import TelethonReactions

# Aiogram
from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l2_interfaces.telegram.aiogram.events import AiogramEvents
from src.l2_interfaces.telegram.aiogram.skills.chats import AiogramChats
from src.l2_interfaces.telegram.aiogram.skills.messages import AiogramMessages
from src.l2_interfaces.telegram.aiogram.skills.moderation import AiogramModeration

# ==========================================
# L3 Agent
# ==========================================

from src.l3_agent.llm.api_keys.rotator import APIKeyRotator
from src.l3_agent.llm.client import LLMClient
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder
from src.l3_agent.react.loop import ReactLoop
from src.l3_agent.heartbeat import Heartbeat
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.skills.schema import ACTION_SCHEMA


class System:
    """
    Корень композиции.
    Собирает все слои системы воедино, управляет жизненным циклом.
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

        # Хранилище компонентов, у которых есть методы start() и stop()
        self._lifecycle_components = []

        # Заглушки для безопасного вызова stop() при раннем падении
        self.sql = None
        self.vector = None
        self.heartbeat = None

    def setup_l0_state(self):
        """Создает стейты. Создаем все, даже если интерфейс выключен (во избежание NoneType)."""
        system_logger.info("[System] Инициализация L0 State.")

        self.agent_state = AgentState(
            llm_model=self.settings.llm.model_name,
            temperature=self.settings.llm.temperature,
            max_react_steps=self.settings.llm.max_react_steps,
        )
        self.os_state = HostOSState()
        self.terminal_state = HostTerminalState()
        self.telethon_state = TelethonState()
        self.aiogram_state = AiogramState()

    async def setup_l1_databases(self):
        """Поднимает базы данных и регистрирует их CRUD-скиллы."""
        system_logger.info("[System] Инициализация L1 Databases.")

        # SQL DB
        self.sql = SQLManager(db_path=self.local_data_dir / "sql_db" / "agent.db")
        await self.sql.connect()

        register_instance(self.sql.tasks)
        register_instance(self.sql.personality_traits)

        # Vector DB
        self.vector = VectorManager(
            db_path=self.local_data_dir / "vector_db",
            embedding_model_path=self.local_data_dir / "embeddings",
            embedding_model_name=self.settings.system.vector_db.embedding_model,
            vector_size=self.settings.system.vector_db.vector_size,
        )
        await self.vector.connect()

        register_instance(self.vector.knowledge)
        register_instance(self.vector.thoughts)

    def setup_l2_interfaces(
        self,
        telethon_api_id: str = None,
        telethon_api_hash: str = None,
        aiogram_bot_token: str = None,
    ):
        """Читает конфиг, поднимает нужные интерфейсы и регистрирует их скиллы."""
        system_logger.info("[System] Инициализация L2 Interfaces.")

        # HOST OS
        if self.interfaces_config.host.os.enabled:
            os_client = HostOSClient(
                base_dir=self.root_dir,
                config=self.interfaces_config.host.os,
                state=self.os_state,
            )
            os_events = HostOSEvents(
                host_os_client=os_client, state=self.os_state, event_bus=self.event_bus
            )

            register_instance(HostOSExecution(os_client))
            register_instance(HostOSFiles(os_client))
            register_instance(HostOSNetwork(os_client))
            register_instance(HostOSSystem(os_client))

            self._lifecycle_components.append(os_events)
            system_logger.info("[System] Интерфейс Host OS загружен.")

        # HOST TERMINAL
        if self.interfaces_config.host.terminal.enabled:
            term_client = HostTerminalClient(
                config=self.interfaces_config.host.terminal, state=self.terminal_state
            )
            term_events = HostTerminalEvents(
                client=term_client, state=self.terminal_state, event_bus=self.event_bus
            )

            register_instance(
                HostTerminalMessages(
                    client=term_client,
                    state=self.terminal_state,
                    agent_name=self.settings.identity.agent_name,
                )
            )

            self._lifecycle_components.extend([term_client, term_events])
            system_logger.info("[System] Интерфейс Host Terminal загружен.")

        # TELEGRAM: TELETHON
        if self.interfaces_config.telegram.telethon.enabled:

            if not telethon_api_id or not telethon_api_hash:
                system_logger.error(
                    "[System] TELETHON_API_ID или TELETHON_API_HASH не найдены в .env. Telethon отключен."
                )
            else:
                session_path = str(
                    self.local_data_dir / self.interfaces_config.telegram.telethon.session_name
                )
                tel_client = TelethonClient(
                    state=self.telethon_state,
                    api_id=telethon_api_id,
                    api_hash=telethon_api_hash,
                    session_path=session_path,
                )
                tel_events = TelethonEvents(
                    tg_client=tel_client, state=self.telethon_state, event_bus=self.event_bus
                )

                register_instance(TelethonAccount(tel_client))
                register_instance(TelethonChats(tel_client))
                register_instance(TelethonMessages(tel_client))
                register_instance(TelethonModeration(tel_client))
                register_instance(TelethonPolls(tel_client))
                register_instance(TelethonReactions(tel_client))

                self._lifecycle_components.extend([tel_client, tel_events])
                system_logger.info("[System] Интерфейс Telethon загружен.")

        # TELEGRAM: AIOGRAM
        if self.interfaces_config.telegram.aiogram.enabled:
            if not aiogram_bot_token:
                system_logger.error(
                    "[System] AIOGRAM_BOT_TOKEN не найден в .env. Aiogram отключен."
                )
            else:
                aio_client = AiogramClient(
                    bot_token=aiogram_bot_token, state=self.aiogram_state
                )
                aio_events = AiogramEvents(
                    aiogram_client=aio_client,
                    state=self.aiogram_state,
                    event_bus=self.event_bus,
                )

                register_instance(AiogramChats(aio_client, self.aiogram_state))
                register_instance(AiogramMessages(aio_client))
                register_instance(AiogramModeration(aio_client))

                self._lifecycle_components.extend([aio_client, aio_events])
                system_logger.info("[System] Интерфейс Aiogram загружен.")

    def setup_l3_agent(self, llm_api_url: str, llm_api_keys: list[str]):
        """Сборка мозга агента."""
        system_logger.info("[System] Инициализация L3 Agent.")

        rotator = APIKeyRotator(keys=llm_api_keys)
        llm_client = LLMClient(api_url=llm_api_url, api_keys_rotator=rotator)

        prompt_builder = PromptBuilder(
            prompt_dir=self.root_dir / "src" / "l3_agent" / "prompt"
        )
        context_builder = ContextBuilder(
            host_os_state=self.os_state,
            telethon_state=self.telethon_state,
            aiogram_state=self.aiogram_state,
            terminal_state=self.terminal_state,
            agent_state=self.agent_state,
            sql_ticks=self.sql.ticks,
            sql_tasks=self.sql.tasks,
            sql_traits=self.sql.personality_traits,
            depth_config=self.settings.system.context_depth,
            interfaces_config=self.interfaces_config,
        )

        token_tracker = TokenTracker()

        react_loop = ReactLoop(
            llm_client=llm_client,
            prompt_builder=prompt_builder,
            context_builder=context_builder,
            agent_state=self.agent_state,
            sql_ticks=self.sql.ticks,
            token_tracker=token_tracker,
            tools=ACTION_SCHEMA,
        )

        self.heartbeat = Heartbeat(
            react_loop=react_loop,
            tick_interval_sec=self.settings.system.tick_interval_sec,
            accel_config=self.settings.system.event_acceleration,
        )

        # Связываем шину событий с пульсом агента (мост между L2 и L3)
        self._bridge_events_to_heartbeat()

    def _bridge_events_to_heartbeat(self):
        """Подписывает Heartbeat на все системные события."""

        def create_handler(evt):
            # Замыкание, чтобы передать правильные данные в wake_up
            def handler(**kwargs):
                self.heartbeat.wake_up(level=evt.level, event_name=evt.name, payload=kwargs)

            return handler

        for event in Events.all():
            self.event_bus.subscribe(event, create_handler(event))

    # ===========================================
    # RUN & STOP
    # ===========================================

    async def run(
        self,
        llm_api_url: str,
        llm_api_keys: list[str],
        telethon_api_id: str = None,
        telethon_api_hash: str = None,
        aiogram_bot_token: str = None,
    ):
        """Запуск системы."""

        system_logger.info("[System] Инициализация JAWL.")

        self.setup_l0_state()
        await self.setup_l1_databases()
        self.setup_l2_interfaces(
            telethon_api_id=telethon_api_id,
            telethon_api_hash=telethon_api_hash,
            aiogram_bot_token=aiogram_bot_token,
        )
        self.setup_l3_agent(llm_api_url=llm_api_url, llm_api_keys=llm_api_keys)

        # Запускаем все фоновые задачи (клиенты и слушатели событий)
        for component in self._lifecycle_components:
            await component.start()

        system_logger.info(
            f"[System] Система успешно запущена. Имя агента: {self.settings.identity.agent_name}."
        )
        await self.event_bus.publish(Events.SYSTEM_CORE_START, status="online")

        # Блокирующий цикл жизни агента
        await self.heartbeat.start()

    async def stop(self):
        """Остановка и очистка ресурсов."""
        system_logger.info("[System] Инициирована остановка JAWL.")
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

        if self.vector:
            await self.vector.disconnect()
        if self.sql:
            await self.sql.disconnect()

        system_logger.info("[System] Остановка завершена. Процесс жестоко убит.")


# ===================================================================
# ENTRY POINT
# ===================================================================


async def main():
    # Загружаем переменные окружения
    load_dotenv()

    event_bus = EventBus()
    settings_config, interfaces_config = load_config()

    system = System(
        event_bus=event_bus,
        settings_config=settings_config,
        interfaces_config=interfaces_config,
    )
    try:
        LLM_API_URL = os.getenv("LLM_API_URL", None)
        TELETHON_API_ID = os.getenv("TELETHON_API_ID", None)
        TELETHON_API_HASH = os.getenv("TELETHON_API_HASH", None)
        AIOGRAM_BOT_TOKEN = os.getenv("AIOGRAM_BOT_TOKEN", None)

        # Динамически собираем все ключи, которые начинаются с LLM_API_KEY_
        LLM_API_KEYS = [
            v
            for k, v in sorted(os.environ.items())
            if k.startswith("LLM_API_KEY_") and v.strip()
        ]

        await system.run(
            llm_api_url=LLM_API_URL,
            llm_api_keys=LLM_API_KEYS,
            telethon_api_id=TELETHON_API_ID,
            telethon_api_hash=TELETHON_API_HASH,
            aiogram_bot_token=AIOGRAM_BOT_TOKEN,
        )

    except asyncio.CancelledError:
        pass

    except KeyboardInterrupt:
        system_logger.info("[System] Получен сигнал прерывания.")

    except BaseException as e:
        system_logger.error(f"[System] Критическая ошибка: {type(e).__name__} - {e}")
        system_logger.error(traceback.format_exc())

    finally:
        await system.stop()


if __name__ == "__main__":
    # Защита для Windows
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())

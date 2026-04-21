import os
import asyncio
import traceback
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Any

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
    WebSearchState,
)

# ==========================================
# L1 Databases
# ==========================================

from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.sql.manager import SQLManager

# ==========================================
# L2 Interfaces
# ==========================================

from src.l2_interfaces.initializer import initialize_l2_interfaces

# ==========================================
# L3 Agent
# ==========================================

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator

from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder
from src.l3_agent.context.registry import ContextRegistry, ContextSection
from src.l3_agent.context.rag.memories import RAGMemories

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

        # Хранилище компонентов, которые нужно запустить (например, поллинг Telethon)
        self._lifecycle_components: list[Any] = []

        # Возвращает в конце работы
        self._exit_code: int = 0  # 0 - выключение, 1 - перезагрузка

        # Заглушки для безопасного вызова stop() при раннем падении
        self.sql: Optional[SQLManager] = None
        self.vector: Optional[VectorManager] = None
        self.heartbeat: Optional[Heartbeat] = None
        self.llm_client: Optional[LLMClient] = None

        self.context_registry = ContextRegistry()

    def setup_l0_state(self):
        """Создает стейты. Создает все, даже если интерфейс выключен (во избежание NoneType)."""

        system_logger.info("[System] Инициализация L0 State.")

        self.agent_state = AgentState(
            llm_model=self.settings.llm.model_name,
            temperature=self.settings.llm.temperature,
            max_react_steps=self.settings.llm.max_react_steps,
            heartbeat_interval=self.settings.system.heartbeat_interval,
        )
        self.os_state = HostOSState()
        self.terminal_state = HostTerminalState(number_of_last_messages=15)
        self.telethon_state = TelethonState(number_of_last_chats=15)
        self.aiogram_state = AiogramState(number_of_last_chats=15)
        self.web_search_state = WebSearchState(history_limit=10)

    async def setup_l1_databases(self):
        """Поднимает базы данных и регистрирует их CRUD-скиллы."""

        sys_cfg = self.settings.system
        system_logger.info("[System] Инициализация L1 Databases.")

        # SQL DB
        self.sql = SQLManager(
            db_path=self.local_data_dir / "sql_db" / "agent.db",
            # Ticks
            ticks_limit=sys_cfg.context_depth.ticks,
            detailed_ticks=sys_cfg.context_depth.detailed_ticks,
            tick_action_max_chars=sys_cfg.context_depth.tick_action_max_chars,
            tick_result_max_chars=sys_cfg.context_depth.tick_result_max_chars,
            # Tasks
            max_tasks=sys_cfg.sql.tasks.max_tasks,
            # Mental State
            max_mental_state_entities=sys_cfg.sql.mental_states.max_entities,
            # Personality Traits
            max_traits=sys_cfg.sql.personality_traits.max_traits,
            # Drives
            drives_enabled=sys_cfg.sql.drives.enabled,
            decay_rate=sys_cfg.sql.drives.decay_rate,
            decay_interval_sec=sys_cfg.sql.drives.decay_interval_sec,
            max_history_drives=sys_cfg.sql.drives.max_reflections_history,
            max_custom_drives=sys_cfg.sql.drives.max_custom_drives,
            # Время
            timezone=sys_cfg.timezone,
        )
        await self.sql.connect()

        # =========================================================
        # ДИНАМИЧЕСКАЯ РЕГИСТРАЦИЯ SQL НАВЫКОВ И КОНТЕКСТА
        # =========================================================

        # DRIVES
        if sys_cfg.sql.drives.enabled:
            register_instance(self.sql.drives)
            self.context_registry.register_provider(
                "sql_drives", self.sql.drives.get_context_block, section=ContextSection.DRIVES
            )

        # PERSONALITY TRAITS
        if sys_cfg.sql.personality_traits.enabled:
            register_instance(self.sql.personality_traits)
            self.context_registry.register_provider(
                "sql_traits", self.sql.personality_traits.get_context_block, section=ContextSection.TRAITS
            )

        # TASKS
        if sys_cfg.sql.tasks.enabled:
            register_instance(self.sql.tasks)
            self.context_registry.register_provider(
                "sql_tasks", self.sql.tasks.get_context_block, section=ContextSection.TASKS
            )

        # MENTAL STATES
        if sys_cfg.sql.mental_states.enabled:
            register_instance(self.sql.mental_states)
            self.context_registry.register_provider(
                "sql_mental_states", self.sql.mental_states.get_context_block, section=ContextSection.MENTAL_STATES
            )

        # Базовые вещи регистрируются всегда
        self.context_registry.register_provider(
            "sql_ticks", self.sql.ticks.get_context_block, section=ContextSection.RECENT_TICKS
        )
        self.context_registry.register_provider(
            "agent_state", self.agent_state.get_context_block, section=ContextSection.AGENT_STATE
        )

        # Vector DB
        self.vector = VectorManager(
            db_path=self.local_data_dir / "vector_db",
            embedding_model_path=self.local_data_dir / "embeddings",
            embedding_model_name=self.settings.system.vector_db.embedding_model,
            vector_size=self.settings.system.vector_db.vector_size,
            similarity_threshold=self.settings.system.vector_db.similarity_threshold,
            timezone=self.settings.system.timezone,
        )
        await self.vector.connect()

        # Регистрация навыков для агента
        register_instance(self.vector.knowledge)
        register_instance(self.vector.thoughts)

    def setup_l2_interfaces(
        self,
        telethon_api_id: Optional[str] = None,
        telethon_api_hash: Optional[str] = None,
        aiogram_bot_token: Optional[str] = None,
    ):
        """Читает конфиг, поднимает нужные интерфейсы и регистрирует их скиллы."""

        system_logger.info("[System] Инициализация L2 Interfaces.")

        env_vars = {
            "TELETHON_API_ID": telethon_api_id,
            "TELETHON_API_HASH": telethon_api_hash,
            "AIOGRAM_BOT_TOKEN": aiogram_bot_token,
        }

        # Вся магия сборки интерфейсов скрыта здесь
        components = initialize_l2_interfaces(self, env_vars)
        self._lifecycle_components.extend(components)

    def setup_l3_agent(self, llm_api_url: str, llm_api_keys: list[str]):
        """Сборка мозга агента."""
        system_logger.info("[System] Инициализация L3 Agent.")

        rotator = APIKeyRotator(keys=llm_api_keys)
        self.llm_client = LLMClient(api_url=llm_api_url, api_keys_rotator=rotator)

        prompt_builder = PromptBuilder(
            prompt_dir=self.root_dir / "src" / "l3_agent" / "prompt"
        )

        # Поднимаем RAG-провайдер и регистрируем его
        rag_memories = RAGMemories(
            vector_knowledge=self.vector.knowledge,
            vector_thoughts=self.vector.thoughts,
            telethon_state=self.telethon_state,
            agent_state=self.agent_state,
            auto_rag_top_k=self.settings.system.vector_db.auto_rag_top_k,
        )
        self.context_registry.register_provider(
            "rag memories", rag_memories.get_context_block, section=ContextSection.RAG_MEMORIES
        )

        # Инициализируем тонкий ContextBuilder
        context_builder = ContextBuilder(
            agent_state=self.agent_state, registry=self.context_registry
        )

        token_tracker = TokenTracker()

        react_loop = ReactLoop(
            llm_client=self.llm_client,
            prompt_builder=prompt_builder,
            context_builder=context_builder,
            agent_state=self.agent_state,
            sql_ticks=self.sql.ticks,
            token_tracker=token_tracker,
            tools=ACTION_SCHEMA,
        )

        self.heartbeat = Heartbeat(
            react_loop=react_loop,
            heartbeat_interval=self.settings.system.heartbeat_interval,
            continuous_cycle=self.settings.system.continuous_cycle,
            accel_config=self.settings.system.event_acceleration,
            timezone=self.settings.system.timezone,
        )

        # Связываем шину событий с пульсом агента (мост между L2 и L3)
        self._bridge_events_to_heartbeat()

    def _bridge_events_to_heartbeat(self):
        """Подписывает Heartbeat на все системные события."""

        def create_handler(evt):
            def handler(**kwargs):
                # Если система уже останавливается — игнорируем любые события
                if evt == Events.SYSTEM_CORE_STOP:
                    return

                self.heartbeat.wake_up(level=evt.level, event_name=evt.name, payload=kwargs)

            return handler

        # Базовая подписка: будим агента на любые события, кроме остановки
        for event in Events.all():
            if event == Events.SYSTEM_CORE_STOP:
                continue
            self.event_bus.subscribe(event, create_handler(event))

        # Специфичные подписки
        def handle_config_update(**kwargs):
            key = kwargs.get("key")
            value = kwargs.get("value")
            if key and value is not None:
                self.heartbeat.update_config(key, value)

        # Если агент решил совершить сэппуку
        def handle_shutdown(**kwargs):
            self._exit_code = 0
            if self.heartbeat:
                self.heartbeat.stop()

        # Если агент запросил перезагрузку
        def handle_reboot(**kwargs):
            self._exit_code = 1
            if self.heartbeat:
                self.heartbeat.stop()

        self.event_bus.subscribe(Events.SYSTEM_SHUTDOWN_REQUESTED, handle_shutdown)
        self.event_bus.subscribe(Events.SYSTEM_REBOOT_REQUESTED, handle_reboot)

        self.event_bus.subscribe(Events.SYSTEM_CONFIG_UPDATED, handle_config_update)

    # ===========================================
    # RUN & STOP
    # ===========================================

    async def run(
        self,
        llm_api_url: str,
        llm_api_keys: list[str],
        telethon_api_id: Optional[str] = None,
        telethon_api_hash: Optional[str] = None,
        aiogram_bot_token: Optional[str] = None,
    ) -> int:
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

        # Запускаем все фоновые задачи (клиенты и слушатели событий) отказоустройство
        started_components = []
        for component in self._lifecycle_components:
            try:
                await component.start()
                started_components.append(component)
            except Exception as e:
                system_logger.error(
                    f"[System] Ошибка при запуске интерфейса {component.__class__.__name__}: {e}. Компонент отключен."
                )

        # Оставляем в пуле только те компоненты, которые успешно запустились (чтобы корректно их стопнуть при выходе)
        self._lifecycle_components = started_components

        system_logger.info(
            f"[System] JAWL успешно запущен. Имя агента: {self.settings.identity.agent_name}."
        )
        await self.event_bus.publish(Events.SYSTEM_CORE_START, status="online")

        # Блокирующий цикл жизни агента
        await self.heartbeat.start()

        return self._exit_code

    async def stop(self) -> None:
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

        # Отрубаем всё к чертям
        if self.vector:
            await self.vector.disconnect()
        if self.sql:
            await self.sql.disconnect()
        if self.event_bus:
            await self.event_bus.stop()
        if self.llm_client:
            await self.llm_client.close()

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

        exit_code = await system.run(
            llm_api_url=LLM_API_URL,
            llm_api_keys=LLM_API_KEYS,
            telethon_api_id=TELETHON_API_ID,
            telethon_api_hash=TELETHON_API_HASH,
            aiogram_bot_token=AIOGRAM_BOT_TOKEN,
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

    asyncio.run(main())

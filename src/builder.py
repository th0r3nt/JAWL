"""
System Builder.

Инкапсулирует сложную логику сборки DI-контейнера и 4 архитектурных слоев JAWL (L0-L3).
Очищает main.py от хардкода инициализации, соблюдая принцип единой ответственности.
"""

from typing import TYPE_CHECKING

from src.utils.logger import system_logger
from src.utils.token_tracker import TokenTracker

from src.l0_state.agent.state import AgentState
from src.l0_state.interfaces.host.os_state import HostOSState
from src.l0_state.interfaces.host.terminal_state import HostTerminalState
from src.l0_state.interfaces.telegram.telethon_state import TelethonState
from src.l0_state.interfaces.telegram.aiogram_state import AiogramState
from src.l0_state.interfaces.web.search_state import WebSearchState
from src.l0_state.interfaces.web.http_state import WebHTTPState
from src.l0_state.interfaces.web.browser_state import WebBrowserState
from src.l0_state.interfaces.web.hooks_state import WebHooksState
from src.l0_state.interfaces.web.rss_state import WebRSSState
from src.l0_state.interfaces.calendar_state import CalendarState
from src.l0_state.interfaces.github_state import GithubState
from src.l0_state.interfaces.email_state import EmailState
from src.l0_state.interfaces.custom_state import CustomDashboardState

from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.sql.manager import SQLManager

from src.l2_interfaces.initializer import initialize_l2_interfaces

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder
from src.l3_agent.context.registry import ContextSection
from src.l3_agent.context.rag.memories import RAGMemories
from src.l3_agent.react.loop import ReactLoop
from src.l3_agent.heartbeat import Heartbeat
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.skills.schema import ACTION_SCHEMA
from src.l3_agent.swarm.skills.report import SubagentReport
from src.l3_agent.swarm.spawn import SwarmManager

if TYPE_CHECKING:
    from src.main import System


class SystemBuilder:
    """Сборщик DI-контейнера и архитектуры агента."""

    def __init__(self, system: "System") -> None:
        self.system = system
        self.sys_cfg = system.settings.system

    def build_l0_state(self) -> None:
        """Создает стейты (приборную панель)."""
        
        system_logger.info("[System] Инициализация L0 State.")
        sys = self.system

        sys.agent_state = AgentState(
            llm_model=sys.settings.llm.main_model,
            temperature=sys.settings.llm.temperature,
            max_react_steps=sys.settings.llm.max_react_steps,
            heartbeat_interval=self.sys_cfg.heartbeat_interval,
            continuous_cycle=self.sys_cfg.continuous_cycle,
            proactive_guidance=self.sys_cfg.proactive_guidance,
            context_ticks=self.sys_cfg.context_depth.ticks,
            context_detailed_ticks=self.sys_cfg.context_depth.detailed_ticks,
        )

        sys.os_state = HostOSState()
        sys.terminal_state = HostTerminalState(
            context_limit=sys.interfaces_config.host.terminal.context_limit
        )
        sys.telethon_state = TelethonState(
            number_of_last_chats=sys.interfaces_config.telegram.telethon.recent_chats_limit,
            private_chat_history_limit=sys.interfaces_config.telegram.telethon.private_chat_history_limit,
        )
        sys.aiogram_state = AiogramState(
            number_of_last_chats=sys.interfaces_config.telegram.aiogram.recent_chats_limit
        )
        sys.github_state = GithubState(
            history_limit=sys.interfaces_config.github.history_limit
        )
        sys.email_state = EmailState(recent_limit=sys.interfaces_config.email.recent_limit)
        sys.web_search_state = WebSearchState(history_limit=10)
        sys.web_http_state = WebHTTPState(history_limit=10)
        sys.web_browser_state = WebBrowserState()
        sys.web_hooks_state = WebHooksState(
            history_limit=sys.interfaces_config.web.hooks.history_limit
        )
        sys.web_rss_state = WebRSSState(
            recent_limit=sys.interfaces_config.web.rss.recent_limit
        )
        sys.calendar_state = CalendarState()
        sys.dashboard_state = CustomDashboardState()

    async def build_l1_databases(self) -> None:
        """Поднимает базы данных и регистрирует их CRUD-скиллы."""

        system_logger.info("[System] Инициализация L1 Databases.")
        sys = self.system

        sys.sql = SQLManager(
            db_path=sys.local_data_dir / "sql" / "db" / "agent.db",
            ticks_limit=self.sys_cfg.context_depth.ticks,
            detailed_ticks=self.sys_cfg.context_depth.detailed_ticks,
            tick_action_max_chars=self.sys_cfg.context_depth.tick_action_max_chars,
            tick_result_max_chars=self.sys_cfg.context_depth.tick_result_max_chars,
            tick_thoughts_short_max_chars=self.sys_cfg.context_depth.tick_thoughts_short_max_chars,
            tick_action_short_max_chars=self.sys_cfg.context_depth.tick_action_short_max_chars,
            tick_result_short_max_chars=self.sys_cfg.context_depth.tick_result_short_max_chars,
            max_tasks=self.sys_cfg.sql.tasks.max_tasks,
            max_mental_state_entities=self.sys_cfg.sql.mental_states.max_entities,
            max_traits=self.sys_cfg.sql.personality_traits.max_traits,
            drives_enabled=self.sys_cfg.sql.drives.enabled,
            decay_rate=self.sys_cfg.sql.drives.decay_rate,
            decay_interval_sec=self.sys_cfg.sql.drives.decay_interval_sec,
            max_history_drives=self.sys_cfg.sql.drives.max_reflections_history,
            max_custom_drives=self.sys_cfg.sql.drives.max_custom_drives,
            timezone=self.sys_cfg.timezone,
        )
        await sys.sql.connect()

        # DRIVES
        if self.sys_cfg.sql.drives.enabled:
            register_instance(sys.sql.drives)
            sys.context_registry.register_provider(
                "sql_drives", sys.sql.drives.get_context_block, section=ContextSection.DRIVES
            )

        # PERSONALITY TRAITS
        if self.sys_cfg.sql.personality_traits.enabled:
            register_instance(sys.sql.personality_traits)
            sys.context_registry.register_provider(
                "sql_traits",
                sys.sql.personality_traits.get_context_block,
                section=ContextSection.TRAITS,
            )

        # TASKS
        if self.sys_cfg.sql.tasks.enabled:
            register_instance(sys.sql.tasks)
            sys.context_registry.register_provider(
                "sql_tasks", sys.sql.tasks.get_context_block, section=ContextSection.TASKS
            )

        # MENTAL STATES
        if self.sys_cfg.sql.mental_states.enabled:
            register_instance(sys.sql.mental_states)
            sys.context_registry.register_provider(
                "sql_mental_states",
                sys.sql.mental_states.get_context_block,
                section=ContextSection.MENTAL_STATES,
            )

        # Базовые вещи регистрируются всегда
        sys.context_registry.register_provider(
            "sql_ticks", sys.sql.ticks.get_context_block, section=ContextSection.RECENT_TICKS
        )
        sys.context_registry.register_provider(
            "agent_state",
            sys.agent_state.get_context_block,
            section=ContextSection.AGENT_STATE,
        )

        # Vector DB
        sys.vector = VectorManager(
            db_path=sys.local_data_dir / "vector" / "db",
            embedding_model_path=sys.local_data_dir / "vector" / "embeddings",
            embedding_model_name=sys.settings.system.vector_db.embedding_model,
            vector_size=sys.settings.system.vector_db.vector_size,
            similarity_threshold=sys.settings.system.vector_db.similarity_threshold,
            timezone=sys.settings.system.timezone,
        )
        await sys.vector.connect()

        register_instance(sys.vector.knowledge)
        register_instance(sys.vector.thoughts)

    def build_l2_interfaces(self, env_vars: dict) -> None:
        """Читает конфиг, поднимает нужные интерфейсы и регистрирует их скиллы."""

        system_logger.info("[System] Инициализация L2 Interfaces.")
        components = initialize_l2_interfaces(self.system, env_vars)
        self.system._lifecycle_components.extend(components)

    def build_l3_agent(self, env_vars: dict) -> None:
        """Сборка мозга агента."""

        system_logger.info("[System] Инициализация L3 Agent.")
        sys_obj = self.system

        llm_api_keys = env_vars.get("LLM_API_KEYS", [])
        llm_api_url = env_vars.get("LLM_API_URL", "")
        sub_llm_api_keys = env_vars.get("SUB_LLM_API_KEYS", [])
        sub_llm_api_url = env_vars.get("SUB_LLM_API_URL", "")

        rotator = APIKeyRotator(keys=llm_api_keys)
        sys_obj.llm_client = LLMClient(api_url=llm_api_url, api_keys_rotator=rotator)

        if sub_llm_api_keys:
            system_logger.info("[System] Обнаружены выделенные ключи для субагентов (Swarm).")
            sub_rotator = APIKeyRotator(keys=sub_llm_api_keys)
            sys_obj.sub_llm_client = LLMClient(
                api_url=sub_llm_api_url or "", api_keys_rotator=sub_rotator
            )
        else:
            sys_obj.sub_llm_client = sys_obj.llm_client

        prompt_builder = PromptBuilder(
            prompt_dir=sys_obj.root_dir / "src" / "l3_agent" / "prompt",
            drives_enabled=self.sys_cfg.sql.drives.enabled,
            tasks_enabled=self.sys_cfg.sql.tasks.enabled,
            traits_enabled=self.sys_cfg.sql.personality_traits.enabled,
            mental_states_enabled=self.sys_cfg.sql.mental_states.enabled,
            swarm_enabled=self.sys_cfg.swarm.enabled,
        )

        rag_memories = RAGMemories(
            vector_knowledge=sys_obj.vector.knowledge,
            vector_thoughts=sys_obj.vector.thoughts,
            telethon_state=sys_obj.telethon_state,
            agent_state=sys_obj.agent_state,
            auto_rag_top_k=sys_obj.settings.system.vector_db.auto_rag_top_k,
            auto_rag_max_query_chars=sys_obj.settings.system.vector_db.auto_rag_max_query_chars,
        )
        sys_obj.context_registry.register_provider(
            "rag memories", rag_memories.get_context_block, section=ContextSection.RAG_MEMORIES
        )

        sys_obj.context_registry.register_provider(
            "custom_dashboard",
            sys_obj.dashboard_state.get_context_block,
            section=ContextSection.INTERFACES,
        )

        context_builder = ContextBuilder(
            agent_state=sys_obj.agent_state, registry=sys_obj.context_registry
        )

        token_tracker = TokenTracker()

        # ReactLoop
        react_loop = ReactLoop(
            llm_client=sys_obj.llm_client,
            prompt_builder=prompt_builder,
            context_builder=context_builder,
            agent_state=sys_obj.agent_state,
            sql_ticks=sys_obj.sql.ticks,
            vector_manager=sys_obj.vector,
            token_tracker=token_tracker,
            tools=ACTION_SCHEMA,
        )

        # Heartbeat
        sys_obj.heartbeat = Heartbeat(
            react_loop=react_loop,
            heartbeat_interval=sys_obj.settings.system.heartbeat_interval,
            continuous_cycle=sys_obj.settings.system.continuous_cycle,
            accel_config=sys_obj.settings.system.event_acceleration,
            timezone=sys_obj.settings.system.timezone,
        )

        # Swarm
        if self.sys_cfg.swarm.enabled:
            report_skill = SubagentReport(
                event_bus=sys_obj.event_bus, sandbox_dir=sys_obj.root_dir / "sandbox"
            )
            register_instance(report_skill)

            swarm_manager = SwarmManager(
                llm_client=sys_obj.sub_llm_client,
                swarm_config=self.sys_cfg.swarm,
                root_dir=sys_obj.root_dir,
                token_tracker=token_tracker,
            )
            register_instance(swarm_manager)
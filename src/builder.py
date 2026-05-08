"""
System Builder.

Инкапсулирует сложную логику сборки DI-контейнера и 4 архитектурных слоев JAWL (L0-L3).
Очищает main.py от хардкода инициализации, соблюдая принцип единой ответственности.
"""

from typing import TYPE_CHECKING

from src.l3_agent.subconscious.orchestrator import SubconsciousOrchestrator
from src.utils.logger import main_logger
from src.utils.token_tracker import TokenTracker

from src.l0_state.agent.state import AgentState
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.terminal.state import HostTerminalState
from src.l2_interfaces.telegram.telethon.state import TelethonState
from src.l2_interfaces.telegram.aiogram.state import AiogramState
from src.l2_interfaces.web.search.state import WebSearchState
from src.l2_interfaces.web.http.state import WebHTTPState
from src.l2_interfaces.web.browser.state import WebBrowserState
from src.l2_interfaces.web.hooks.state import WebHooksState
from src.l2_interfaces.web.rss.state import WebRSSState
from src.l2_interfaces.calendar.state import CalendarState
from src.l2_interfaces.github.state import GithubState
from src.l2_interfaces.email.state import EmailState
from src.l2_interfaces.meta.state import CustomDashboardState
from src.l2_interfaces.code_graph.state import CodeGraphState

from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.sql.manager import SQLManager
from src.l1_databases.graph.manager import GraphManager

from src.l2_interfaces.initializer import initialize_l2_interfaces

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator

from src.l3_agent.prompt.builder import PromptBuilder

from src.l3_agent.context.builder import ContextBuilder
from src.l3_agent.context.registry import ContextSection
from src.l3_agent.context.rag.memories import RAGMemories
from src.l3_agent.context.rag.skills import MemoryRecallSkill

from src.l3_agent.react.loop import ReactLoop
from src.l3_agent.heartbeat import Heartbeat

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.skills.schema import ACTION_SCHEMA

from src.l3_agent.swarm.skills.report import SubagentReport
from src.l3_agent.swarm.spawn import SwarmManager

from src.l3_agent.tot.generator import ToTGenerator
from src.l3_agent.tot.skills import DeepThinkSkill

if TYPE_CHECKING:
    from src.main import System


class SystemBuilder:
    """Сборщик DI-контейнера и архитектуры агента."""

    def __init__(self, system: "System") -> None:
        self.system = system
        self.sys_cfg = system.settings.system

    def build_l0_state(self) -> None:
        """Создает стейты (приборную панель)."""

        main_logger.info("[System] Инициализация L0 State.")
        sys = self.system

        sys.agent_state = AgentState(
            llm_model=sys.settings.llm.main_model,
            temperature=sys.settings.llm.temperature,
            max_react_steps=sys.settings.llm.max_react_steps,
            heartbeat_interval=self.sys_cfg.heartbeat_interval,
            continuous_cycle=self.sys_cfg.continuous_cycle,
            proactive_guidance=self.sys_cfg.proactive_guidance,
            context_high_ticks=self.sys_cfg.context_depth.high_ticks,
            context_medium_ticks=self.sys_cfg.context_depth.medium_ticks,
            context_low_ticks=self.sys_cfg.context_depth.low_ticks,
            subconscious_enabled=self.sys_cfg.subconscious.enabled,
        )

        sys.os_state = HostOSState()
        sys.terminal_state = HostTerminalState(
            context_limit=sys.interfaces_config.host.terminal.context_limit
        )
        sys.code_graph_state = CodeGraphState(data_dir=sys.local_data_dir)
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

        main_logger.info("[System] Инициализация L1 Databases.")
        sys = self.system

        # =================================================================
        # SQL

        sys.sql = SQLManager(
            db_path=sys.local_data_dir / "sql" / "db" / "agent.db",
            notes_max_notes=self.sys_cfg.db.sql.notes.max_notes,
            # Ticks
            high_ticks=self.sys_cfg.context_depth.high_ticks,
            medium_ticks=self.sys_cfg.context_depth.medium_ticks,
            low_ticks=self.sys_cfg.context_depth.low_ticks,
            tick_action_max_chars=self.sys_cfg.context_depth.tick_action_max_chars,
            tick_result_max_chars=self.sys_cfg.context_depth.tick_result_max_chars,
            tick_thoughts_short_max_chars=self.sys_cfg.context_depth.tick_thoughts_short_max_chars,
            tick_action_short_max_chars=self.sys_cfg.context_depth.tick_action_short_max_chars,
            tick_result_short_max_chars=self.sys_cfg.context_depth.tick_result_short_max_chars,
            # Tasks
            max_tasks=self.sys_cfg.db.sql.tasks.max_tasks,
            # Mental States
            max_mental_state_entities=self.sys_cfg.db.sql.mental_states.max_entities,
            # Traits
            max_traits=self.sys_cfg.db.sql.personality_traits.max_traits,
            # Drives
            drives_enabled=self.sys_cfg.db.sql.drives.enabled,
            dynamic_reduction=self.sys_cfg.db.sql.drives.dynamic_reduction,
            decay_rate=self.sys_cfg.db.sql.drives.decay_rate,
            decay_interval_sec=self.sys_cfg.db.sql.drives.decay_interval_sec,
            max_history_drives=self.sys_cfg.db.sql.drives.max_reflections_history,
            max_custom_drives=self.sys_cfg.db.sql.drives.max_custom_drives,
            fundamental_toggles=self.sys_cfg.db.sql.drives.fundamental.model_dump(),
            # Time
            timezone=self.sys_cfg.timezone,
        )
        await sys.sql.connect()

        # Drives
        if self.sys_cfg.db.sql.drives.enabled:
            register_instance(sys.sql.drives)
            sys.context_registry.register_provider(
                "sql_drives", sys.sql.drives.get_context_block, section=ContextSection.DRIVES
            )

        # Personality Traits
        if self.sys_cfg.db.sql.personality_traits.enabled:
            register_instance(sys.sql.personality_traits)
            sys.context_registry.register_provider(
                "sql_traits",
                sys.sql.personality_traits.get_context_block,
                section=ContextSection.TRAITS,
            )

        # Tasks
        if self.sys_cfg.db.sql.tasks.enabled:
            register_instance(sys.sql.tasks)
            sys.context_registry.register_provider(
                "sql_tasks", sys.sql.tasks.get_context_block, section=ContextSection.TASKS
            )

        # Notes
        if self.sys_cfg.db.sql.notes.enabled:
            register_instance(sys.sql.notes)
            sys.context_registry.register_provider(
                "sql_notes", sys.sql.notes.get_context_block, section=ContextSection.NOTES
            )

        # Mental States
        if self.sys_cfg.db.sql.mental_states.enabled:
            register_instance(sys.sql.mental_states)
            sys.context_registry.register_provider(
                "sql_mental_states",
                sys.sql.mental_states.get_context_block,
                section=ContextSection.MENTAL_STATES,
            )

        # Регистрируются всегда
        sys.context_registry.register_provider(
            "sql_ticks", sys.sql.ticks.get_context_block, section=ContextSection.RECENT_TICKS
        )
        sys.context_registry.register_provider(
            "agent_state",
            sys.agent_state.get_context_block,
            section=ContextSection.AGENT_STATE,
        )

        # =================================================================
        # Vector DB

        sys.vector = VectorManager(
            db_path=sys.local_data_dir / "vector" / "db",
            embedding_model_path=sys.local_data_dir / "vector" / "embeddings",
            embedding_model_name=self.sys_cfg.db.vector.embedding_model,
            vector_size=self.sys_cfg.db.vector.vector_size,
            similarity_threshold=self.sys_cfg.db.vector.similarity_threshold,
            timezone=self.sys_cfg.timezone,
        )
        await sys.vector.connect()

        register_instance(sys.vector.knowledge)
        register_instance(sys.vector.thoughts)

        # =================================================================
        # Graph DB

        sys.graph = GraphManager(
            db_path=sys.local_data_dir / "graph" / "agent_graph.db",
            max_nodes=self.sys_cfg.db.graph.max_nodes,
        )
        await sys.graph.connect()

        register_instance(sys.graph.crud)

    def build_l2_interfaces(self, env_vars: dict) -> None:
        """Читает конфиг, поднимает нужные интерфейсы и регистрирует их скиллы."""

        main_logger.info("[System] Инициализация L2 Interfaces.")
        components = initialize_l2_interfaces(self.system, env_vars)
        self.system._lifecycle_components.extend(components)

    def build_l3_agent(self, env_vars: dict) -> None:
        """Сборка мозга агента."""

        main_logger.info("[System] Инициализация L3 Agent.")
        sys_obj = self.system

        llm_api_keys = env_vars.get("LLM_API_KEYS", [])
        llm_api_url = env_vars.get("LLM_API_URL", "")
        sub_llm_api_keys = env_vars.get("SUB_LLM_API_KEYS", [])
        sub_llm_api_url = env_vars.get("SUB_LLM_API_URL", "")

        rotator = APIKeyRotator(keys=llm_api_keys)
        sys_obj.llm_client = LLMClient(api_url=llm_api_url, api_keys_rotator=rotator)

        if sub_llm_api_keys:
            main_logger.info("[System] Обнаружены выделенные ключи для субагентов (Swarm).")
            sub_rotator = APIKeyRotator(keys=sub_llm_api_keys)
            sys_obj.sub_llm_client = LLMClient(
                api_url=sub_llm_api_url or "", api_keys_rotator=sub_rotator
            )
        else:
            sys_obj.sub_llm_client = sys_obj.llm_client

        # ======================================================================
        # Prompt Builder

        prompt_builder = PromptBuilder(
            prompt_dir=sys_obj.root_dir / "src" / "l3_agent" / "prompt",
            drives_enabled=self.sys_cfg.db.sql.drives.enabled,
            tasks_enabled=self.sys_cfg.db.sql.tasks.enabled,
            traits_enabled=self.sys_cfg.db.sql.personality_traits.enabled,
            mental_states_enabled=self.sys_cfg.db.sql.mental_states.enabled,
            notes_enabled=self.sys_cfg.db.sql.notes.enabled,
            swarm_enabled=self.sys_cfg.swarm.enabled,
            tot_enabled=self.sys_cfg.tree_of_thoughts.enabled,
            subconscious_enabled=self.sys_cfg.subconscious.enabled,
        )

        # ======================================================================
        # RAG

        rag_memories = RAGMemories(
            vector_knowledge=sys_obj.vector.knowledge,
            vector_thoughts=sys_obj.vector.thoughts,
            graph_manager=sys_obj.graph,
            embedding_model=sys_obj.vector.embedding,
            telethon_state=sys_obj.telethon_state,
            agent_state=sys_obj.agent_state,
            rag_config=self.sys_cfg.context_depth.rag,
        )
        sys_obj.context_registry.register_provider(
            "rag memories", rag_memories.get_context_block, section=ContextSection.RAG_MEMORIES
        )

        sys_obj.context_registry.register_provider(
            "custom_dashboard",
            sys_obj.dashboard_state.get_context_block,
            section=ContextSection.INTERFACES,
        )

        register_instance(MemoryRecallSkill(rag_memories.orchestrator))

        # ======================================================================
        # Context Builder

        context_builder = ContextBuilder(
            agent_state=sys_obj.agent_state,
            registry=sys_obj.context_registry,
            subconscious_config=self.sys_cfg.subconscious,
        )

        # ======================================================================
        # Token Tracker

        token_tracker = TokenTracker()

        # ======================================================================
        # Tree of Thoughts

        tot_generator = None
        if self.sys_cfg.tree_of_thoughts.enabled:
            tot_generator = ToTGenerator(
                llm_client=sys_obj.sub_llm_client,
                model_name=self.sys_cfg.tree_of_thoughts.llm_model,
                branches_count=self.sys_cfg.tree_of_thoughts.branches,
                simulations_per_branch=self.sys_cfg.tree_of_thoughts.simulations_per_branch,
                max_depth=self.sys_cfg.tree_of_thoughts.max_depth,
                prompt_builder=prompt_builder,
                context_registry=sys_obj.context_registry,
                agent_state=sys_obj.agent_state,
                sql_ticks=sys_obj.sql.ticks,
                token_tracker=token_tracker,
                root_dir=sys_obj.root_dir,
                timezone=self.sys_cfg.timezone,
            )

            # Регистрируем ручной навык, если режим позволяет
            if self.sys_cfg.tree_of_thoughts.mode in ("manual", "hybrid"):
                register_instance(DeepThinkSkill(tot_generator))

        # ======================================================================
        # Subconscious (Подсознание)

        if self.sys_cfg.subconscious.enabled:
            subc_orch = SubconsciousOrchestrator(
                config=self.sys_cfg.subconscious,
                llm_client=sys_obj.sub_llm_client,  # Используем дешевую модель, как у Swarm
                sql_manager=sys_obj.sql,
                vector_manager=sys_obj.vector,
                graph_manager=sys_obj.graph,
                sql_ticks=sys_obj.sql.ticks,
                token_tracker=token_tracker,
                event_bus=sys_obj.event_bus,
                agent_state=sys_obj.agent_state,
                root_dir=sys_obj.root_dir,
            )
            # Подписываем на ивенты
            subc_orch.setup_routing()
            # Опционально можно сохранить ссылку в sys_obj, если понадобится вызывать напрямую
            sys_obj.subconscious_orchestrator = subc_orch

        # ======================================================================
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
            event_bus=sys_obj.event_bus,
            tot_config=self.sys_cfg.tree_of_thoughts,
            tot_generator=tot_generator,
        )

        # ======================================================================
        # Heartbeat

        sys_obj.heartbeat = Heartbeat(
            react_loop=react_loop,
            heartbeat_interval=sys_obj.settings.system.heartbeat_interval,
            continuous_cycle=sys_obj.settings.system.continuous_cycle,
            accel_config=sys_obj.settings.system.event_acceleration,
            timezone=sys_obj.settings.system.timezone,
        )

        # ======================================================================
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

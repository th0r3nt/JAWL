"""
System Builder.

Builder pattern (Fluent Interface) for assembling the DI container.
Populates the passed SystemContainer with ready-made subsystems.
"""

from typing import Dict, Optional

from src.utils.logger import main_logger
from src.utils.token_tracker import TokenTracker

from src.system.container import SystemContainer

from src.l0_state.agent.state import AgentState

from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.sql.manager import SQLManager
from src.l1_databases.graph.manager import GraphManager

from src.l2_interfaces.initializer import initialize_l2_interfaces

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator
from src.l3_agent.llm.executor import LLMExecutor
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder
from src.l3_agent.context.registry import ContextRegistry, ContextSection
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
from src.l3_agent.subconscious.orchestrator import SubconsciousOrchestrator


class SystemBuilder:
    """
    Agent architecture builder. Populates SystemContainer.
    """

    def __init__(self, container: SystemContainer) -> None:
        self.container = container
        self.system_config = container.settings.system

    def with_l0_states(self) -> "SystemBuilder":
        """
        Creates interface states.
        """

        main_logger.info("[System] Initializing L0 State.")

        self.container.agent_state = AgentState(
            llm_model=self.container.settings.llm.main_model,
            temperature=self.container.settings.llm.temperature,
            max_react_steps=self.container.settings.llm.max_react_steps,
            heartbeat_interval=self.system_config.heartbeat_interval,
            continuous_cycle=self.system_config.continuous_cycle,
            proactive_guidance=self.system_config.proactive_guidance,
            context_high_ticks=self.system_config.context_depth.high_ticks,
            context_medium_ticks=self.system_config.context_depth.medium_ticks,
            context_low_ticks=self.system_config.context_depth.low_ticks,
            subconscious_enabled=self.system_config.subconscious.enabled,
        )

        self.container.context_registry = ContextRegistry()
        return self

    async def with_l1_databases(self) -> "SystemBuilder":
        """Starts databases and registers their CRUD skills."""
        main_logger.info("[System] Initializing L1 Databases.")

        # SQL
        self.container.sql = SQLManager(
            db_path=self.container.local_data_dir / "sql" / "db" / "agent.db",
            notes_max_notes=self.system_config.db.sql.notes.max_notes,
            high_ticks=self.system_config.context_depth.high_ticks,
            medium_ticks=self.system_config.context_depth.medium_ticks,
            low_ticks=self.system_config.context_depth.low_ticks,
            tick_action_max_chars=self.system_config.context_depth.tick_action_max_chars,
            tick_result_max_chars=self.system_config.context_depth.tick_result_max_chars,
            tick_thoughts_short_max_chars=self.system_config.context_depth.tick_thoughts_short_max_chars,
            tick_action_short_max_chars=self.system_config.context_depth.tick_action_short_max_chars,
            tick_result_short_max_chars=self.system_config.context_depth.tick_result_short_max_chars,
            max_tasks=self.system_config.db.sql.tasks.max_tasks,
            max_mental_state_entities=self.system_config.db.sql.mental_states.max_entities,
            max_traits=self.system_config.db.sql.personality_traits.max_traits,
            drives_enabled=self.system_config.db.sql.drives.enabled,
            dynamic_reduction=self.system_config.db.sql.drives.dynamic_reduction,
            pause_on_offline=self.system_config.db.sql.drives.pause_on_offline,
            max_history_drives=self.system_config.db.sql.drives.max_reflections_history,
            max_custom_drives=self.system_config.db.sql.drives.max_custom_drives,
            fundamental_config=self.system_config.db.sql.drives.fundamental.model_dump(),
            hypotheses_enabled=self.system_config.db.sql.hypotheses.enabled,
            max_clusters_hypotheses=self.system_config.db.sql.hypotheses.max_clusters,
            max_hypotheses=self.system_config.db.sql.hypotheses.max_hypotheses,
            timezone=self.system_config.timezone,
        )
        await self.container.sql.connect()

        if self.system_config.db.sql.drives.enabled:
            register_instance(self.container.sql.drives)
            self.container.context_registry.register_provider(
                "sql_drives",
                self.container.sql.drives.get_context_block,
                section=ContextSection.DRIVES,
            )

        if self.system_config.db.sql.personality_traits.enabled:
            register_instance(self.container.sql.personality_traits)
            self.container.context_registry.register_provider(
                "sql_traits",
                self.container.sql.personality_traits.get_context_block,
                section=ContextSection.TRAITS,
            )

        if self.system_config.db.sql.tasks.enabled:
            register_instance(self.container.sql.tasks)
            self.container.context_registry.register_provider(
                "sql_tasks",
                self.container.sql.tasks.get_context_block,
                section=ContextSection.TASKS,
            )

        if self.system_config.db.sql.notes.enabled:
            register_instance(self.container.sql.notes)
            self.container.context_registry.register_provider(
                "sql_notes",
                self.container.sql.notes.get_context_block,
                section=ContextSection.NOTES,
            )

        if self.system_config.db.sql.mental_states.enabled:
            register_instance(self.container.sql.mental_states)
            self.container.context_registry.register_provider(
                "sql_mental_states",
                self.container.sql.mental_states.get_context_block,
                section=ContextSection.MENTAL_STATES,
            )

        if self.system_config.db.sql.hypotheses.enabled:
            register_instance(self.container.sql.hypotheses)
            self.container.context_registry.register_provider(
                "sql_hypotheses",
                self.container.sql.hypotheses.get_context_block,
                section=ContextSection.HYPOTHESES,
            )

        register_instance(self.container.sql.ticks)
        self.container.context_registry.register_provider(
            "sql_ticks",
            self.container.sql.ticks.get_context_block,
            section=ContextSection.RECENT_TICKS,
        )
        self.container.context_registry.register_provider(
            "agent_state",
            self.container.agent_state.get_context_block,
            section=ContextSection.AGENT_STATE,
        )

        self.container.vector = VectorManager(
            db_path=self.container.local_data_dir / "vector" / "db",
            embedding_model_path=self.container.local_data_dir / "vector" / "embeddings",
            embedding_model_name=self.system_config.db.vector.embedding_model,
            vector_size=self.system_config.db.vector.vector_size,
            similarity_threshold=self.system_config.db.vector.similarity_threshold,
            timezone=self.system_config.timezone,
        )
        await self.container.vector.connect()
        register_instance(self.container.vector.knowledge)
        register_instance(self.container.vector.thoughts)

        self.container.graph = GraphManager(
            db_path=self.container.local_data_dir / "graph" / "agent_graph.db",
            max_nodes=self.system_config.db.graph.max_nodes,
        )
        await self.container.graph.connect()
        register_instance(self.container.graph.crud)

        return self

    def with_l2_interfaces(self, env_vars: Dict[str, Optional[str]]) -> "SystemBuilder":
        """Reads config, initializes required interfaces and registers their skills."""
        main_logger.info("[System] Initializing L2 Interfaces.")

        # These components will later be started by SystemOrchestrator
        components = initialize_l2_interfaces(self.container, env_vars)
        self.container.lifecycle_components.extend(components)
        return self

    def with_l3_agent(self, env_vars: Dict[str, Optional[str]]) -> "SystemBuilder":
        """Assembles the agent brain."""
        main_logger.info("[System] Initializing L3 Agent.")

        llm_api_keys = env_vars.get("LLM_API_KEYS", [])
        llm_api_url = env_vars.get("LLM_API_URL", "")
        sub_llm_api_keys = env_vars.get("SUB_LLM_API_KEYS", [])
        sub_llm_api_url = env_vars.get("SUB_LLM_API_URL", "")
        proxy_url = env_vars.get("PROXY_URL")

        rotator = APIKeyRotator(keys=llm_api_keys)
        self.container.llm_client = LLMClient(
            api_url=llm_api_url, api_keys_rotator=rotator, proxy_url=proxy_url
        )

        if sub_llm_api_keys:
            main_logger.info("[System] Found dedicated keys for subagents (Swarm).")
            sub_rotator = APIKeyRotator(keys=sub_llm_api_keys)
            self.container.sub_llm_client = LLMClient(
                api_url=sub_llm_api_url or "",
                api_keys_rotator=sub_rotator,
                proxy_url=proxy_url,
            )
        else:
            self.container.sub_llm_client = self.container.llm_client

        prompt_builder = PromptBuilder(
            prompt_dir=self.container.root_dir / "src" / "l3_agent" / "prompt",
            language=self.container.settings.llm.language,
            drives_enabled=self.system_config.db.sql.drives.enabled,
            tasks_enabled=self.system_config.db.sql.tasks.enabled,
            traits_enabled=self.system_config.db.sql.personality_traits.enabled,
            mental_states_enabled=self.system_config.db.sql.mental_states.enabled,
            notes_enabled=self.system_config.db.sql.notes.enabled,
            swarm_enabled=self.system_config.swarm.enabled,
            tot_enabled=self.system_config.tree_of_thoughts.enabled,
            subconscious_enabled=self.system_config.subconscious.enabled,
            hypotheses_enabled=self.system_config.db.sql.hypotheses.enabled,
        )

        rag_memories = RAGMemories(
            vector_knowledge=self.container.vector.knowledge,
            vector_thoughts=self.container.vector.thoughts,
            graph_manager=self.container.graph,
            embedding_model=self.container.vector.embedding,
            agent_state=self.container.agent_state,
            rag_config=self.system_config.context_depth.rag,
        )
        self.container.context_registry.register_provider(
            "rag memories", rag_memories.get_context_block, section=ContextSection.RAG_MEMORIES
        )
        if "dashboard" in self.container.l0_states:
            self.container.context_registry.register_provider(
                "custom_dashboard",
                self.container.l0_states["dashboard"].get_context_block,
                section=ContextSection.INTERFACES,
            )
        register_instance(MemoryRecallSkill(rag_memories.orchestrator))

        context_builder = ContextBuilder(
            agent_state=self.container.agent_state,
            registry=self.container.context_registry,
            subconscious_config=self.system_config.subconscious,
        )

        token_tracker = TokenTracker()
        min_call_interval = self.container.settings.llm.min_call_interval_sec

        main_llm_executor = LLMExecutor(
            self.container.llm_client,
            token_tracker,
            min_call_interval_sec=min_call_interval,
        )
        sub_llm_executor = LLMExecutor(
            self.container.sub_llm_client,
            token_tracker,
            min_call_interval_sec=min_call_interval,
        )

        tot_generator = None
        if self.system_config.tree_of_thoughts.enabled:
            tot_generator = ToTGenerator(
                executor=sub_llm_executor,
                model_name=self.system_config.tree_of_thoughts.llm_model,
                branches_count=self.system_config.tree_of_thoughts.branches,
                simulations_per_branch=self.system_config.tree_of_thoughts.simulations_per_branch,
                max_depth=self.system_config.tree_of_thoughts.max_depth,
                prompt_builder=prompt_builder,
                context_registry=self.container.context_registry,
                agent_state=self.container.agent_state,
                sql_ticks=self.container.sql.ticks,
                root_dir=self.container.root_dir,
                timezone=self.system_config.timezone,
            )
            if self.system_config.tree_of_thoughts.mode in ("manual", "hybrid"):
                register_instance(DeepThinkSkill(tot_generator))

        if self.system_config.subconscious.enabled:
            subc_orch = SubconsciousOrchestrator(
                config=self.system_config.subconscious,
                executor=sub_llm_executor,
                sql_manager=self.container.sql,
                vector_manager=self.container.vector,
                graph_manager=self.container.graph,
                event_bus=self.container.event_bus,
                agent_state=self.container.agent_state,
                root_dir=self.container.root_dir,
            )
            subc_orch.setup_routing()
            self.container.subconscious_orchestrator = subc_orch

        react_loop = ReactLoop(
            executor=main_llm_executor,
            prompt_builder=prompt_builder,
            context_builder=context_builder,
            agent_state=self.container.agent_state,
            sql_ticks=self.container.sql.ticks,
            vector_manager=self.container.vector,
            tools=ACTION_SCHEMA,
            event_bus=self.container.event_bus,
            tot_config=self.system_config.tree_of_thoughts,
            tot_generator=tot_generator,
        )

        self.container.heartbeat = Heartbeat(
            react_loop=react_loop,
            heartbeat_interval=self.container.settings.system.heartbeat_interval,
            continuous_cycle=self.container.settings.system.continuous_cycle,
            accel_config=self.container.settings.system.event_acceleration,
            timezone=self.container.settings.system.timezone,
        )

        if self.system_config.swarm.enabled:
            report_skill = SubagentReport(
                event_bus=self.container.event_bus,
                sandbox_dir=self.container.root_dir / "sandbox",
            )
            register_instance(report_skill)

            swarm_manager = SwarmManager(
                executor=sub_llm_executor,
                swarm_config=self.system_config.swarm,
                root_dir=self.container.root_dir,
            )
            register_instance(swarm_manager)

        return self

    def build(self) -> SystemContainer:
        """Returns fully assembled container."""
        return self.container

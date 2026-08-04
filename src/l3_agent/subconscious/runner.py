"""
Subconscious Runner.

Implements a lightweight, stateless ReAct loop for background database
maintenance tasks (Consolidation, Reflection, Forgetting).
"""

import asyncio
from pathlib import Path
from typing import List, Tuple, Optional

from src.utils.logger import subc_logger

from src.l3_agent.llm.executor import LLMExecutor

from src.l3_agent.skills.schema import AgentResponse, ActionCall, ACTION_SCHEMA, parse_llm_json
from src.l3_agent.skills.registry import _REGISTRY, call_skill
from src.l3_agent.subconscious.schema import Pattern

from src.l1_databases.sql.manager import SQLManager
from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.graph.manager import GraphManager
from src.l1_databases.graph.schema import GRAPH_NODE_TABLE


class SubconsciousRunner:
    """Lightweight ReAct loop for background database tasks."""

    def __init__(
        self,
        executor: LLMExecutor,
        model_name: str,
        sql_manager: SQLManager,
        vector_manager: VectorManager,
        graph_manager: GraphManager,
        root_dir: Path,
        max_steps: int = 4,
    ) -> None:
        """
        Initializes the background runner.
        """
        self.executor = executor

        self.model_name = model_name
        self.sql = sql_manager
        self.vector = vector_manager
        self.graph = graph_manager
        self.root_dir = root_dir
        self.max_steps = max_steps

    # ========================================================
    # MAIN RUN LOOP
    # ========================================================

    async def run(self, pattern: Pattern, ticks_to_analyze: int) -> None:
        """Launches a miniature subconscious reasoning cycle."""
        log = f"[Subconscious] Starting pattern {pattern.value.upper()} (LLM: {self.model_name})."
        subc_logger.info(log)

        prompt = self._get_prompt(pattern)
        allowed_skills_doc = self._get_allowed_skills(pattern)

        context = await self._build_dynamic_context(pattern, ticks_to_analyze)

        full_user_msg = f"{context}\n\n## AVAILABLE SKILLS\nYou are allowed to use strictly the following tools:\n{allowed_skills_doc}"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": full_user_msg},
        ]

        for step in range(self.max_steps):
            await asyncio.to_thread(self._dump_context_to_file, messages, pattern)

            raw_answer = await self.executor.execute(
                model_name=self.model_name,
                messages=messages,
                temperature=0.5,
                logger=subc_logger,
                log_prefix=f"[{pattern.value.upper()}]",
                tools=ACTION_SCHEMA,
            )

            if not raw_answer:
                break

            parsed, error = self._parse_response(raw_answer)
            if error:
                log_err = f"[Subconscious] Pattern {pattern.value.upper()} JSON parse error: {error}"
                subc_logger.warning(log_err)
                subc_logger.debug(f"[Subconscious] Raw answer: {raw_answer}")

                messages.append({"role": "assistant", "content": raw_answer})
                messages.append({"role": "user", "content": f"System Error: {error}"})
                continue

            if not parsed.actions:
                log = f"[Subconscious] Pattern {pattern.value.upper()} successfully completed operations."
                subc_logger.info(log)
                break

            results = await self._execute_actions(parsed.actions, pattern)
            messages.append({"role": "assistant", "content": raw_answer})
            messages.append({"role": "user", "content": results})

        log = f"[Subconscious] Cycle of pattern {pattern.value.upper()} concluded."
        subc_logger.debug(log)

    # ========================================================
    # CONTEXT BUILDER STRATEGIES
    # ========================================================

    async def _build_ticks_context(self, limit: int) -> str:
        """Gathers recent ticks (used by Consolidation)."""
        return await self.sql.ticks.get_full_context_block(limit=limit)

    async def _build_reflection_context(self, limit: int) -> str:
        """Gathers ticks + active CRM state and personality traits (used by Reflection)."""
        ticks_ctx = await self._build_ticks_context(limit)

        ms_res = await self.sql.mental_states.get_mental_states()
        tr_res = await self.sql.personality_traits.get_traits()

        return f"{ticks_ctx}\n\n{ms_res.message}\n\n{tr_res.message}"

    async def _build_forgetting_context(self, limit: int) -> str:
        """Gathers database dumps for garbage collection (used by Forgetting)."""
        k_res = await self.vector.knowledge.get_all_knowledge(limit=limit)
        t_res = await self.vector.thoughts.get_all_thoughts(limit=limit)

        def _get_graph_nodes():
            try:
                res = self.graph.db.conn.execute(
                    f"MATCH (n:{GRAPH_NODE_TABLE}) RETURN n.name, n.category, n.description LIMIT {limit}"
                )
                nodes = []
                while res.has_next():
                    row = res.get_next()
                    nodes.append(f"- [{row[1]}] {row[0]}: {row[2]}")
                return "\n".join(nodes) if nodes else "Graph is empty."
            except Exception:
                return "Graph is empty or unavailable."

        graph_str = await asyncio.to_thread(_get_graph_nodes)

        return (
            f"## VECTOR KNOWLEDGE (Recent {limit})\n{k_res.message}\n\n"
            f"## VECTOR THOUGHTS (Recent {limit})\n{t_res.message}\n\n"
            f"## GRAPH CONCEPTS (Recent {limit})\n{graph_str}"
        )

    async def _build_dynamic_context(self, pattern: Pattern, limit: int) -> str:
        """Context router."""
        if pattern == Pattern.CONSOLIDATION:
            return await self._build_ticks_context(limit)

        elif pattern == Pattern.REFLECTION:
            return await self._build_reflection_context(limit)
        elif pattern == Pattern.FORGETTING:
            return await self._build_forgetting_context(limit)

        return "No data."

    # ========================================================
    # Private Helpers
    # ========================================================

    def _parse_response(
        self, raw_answer: str
    ) -> Tuple[Optional[AgentResponse], Optional[str]]:
        return parse_llm_json(raw_answer)

    async def _execute_actions(self, actions: List[ActionCall], pattern: Pattern) -> str:
        results = []
        for act in actions:
            item = _REGISTRY.get(act.tool_name)
            if not item or pattern not in item.get("subconscious", []):
                results.append(
                    f"* {act.tool_name}: Access denied. Tool is not allowed for the {pattern.value.upper()} pattern."
                )
                continue

            try:
                res = await call_skill(act.tool_name, act.parameters, logger=subc_logger)
                results.append(f"* {act.tool_name}: {res.message}")
            except Exception as e:
                results.append(f"* {act.tool_name}: Internal error - {e}")

        return "\n".join(results)

    def _get_allowed_skills(self, pattern: Pattern) -> str:
        allowed_docs = []
        for name, data in _REGISTRY.items():
            if pattern in data.get("subconscious", []):
                allowed_docs.append(data["doc_string"])
        return "\n".join(allowed_docs) if allowed_docs else "No tools available."

    def _get_prompt(self, pattern: Pattern) -> str:
        prompt_path = (
            self.root_dir
            / "src"
            / "l3_agent"
            / "subconscious"
            / "prompt"
            / f"{pattern.name}.md"
        )
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8").strip()
        return f"You are a background subconscious process ({pattern.value.upper()})."

    def _dump_context_to_file(self, messages: list, pattern: Pattern) -> None:
        """Dumps subconscious prompt to a Markdown file for debugging."""
        from src.utils._tools import dump_prompt_to_file

        meta = f"# SUBCONSCIOUS DUMP: {pattern.value.upper()}"
        dump_prompt_to_file(
            f"logs/prompts/{pattern.value}_prompt.md", messages, meta_header=meta
        )

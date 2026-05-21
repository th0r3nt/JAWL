"""
Tree of Thoughts (ToT) Generator.

Gathers context from active registries, injects raw historical action logs,
and invokes the LLM using a custom JSON schema to simulate recursive tree branches.
"""

import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.utils.logger import tot_logger
from src.utils._tools import dump_prompt_to_file

from src.l0_state.agent.state import AgentState

from src.l1_databases.sql.management.ticks import SQLTicks

from src.l3_agent.llm.executor import LLMExecutor

from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.registry import ContextRegistry, ContextSection
from src.l3_agent.tot.schema import TOT_SCHEMA, TreeResponse, ThoughtBranch


class ToTGenerator:
    """Strategic thought tree simulator and builder."""

    def __init__(
        self,
        executor: LLMExecutor,
        model_name: str,
        prompt_builder: PromptBuilder,
        context_registry: ContextRegistry,
        agent_state: AgentState,
        sql_ticks: SQLTicks,
        root_dir: Path,
        timezone: int,
        branches_count: int,
        simulations_per_branch: int,
        max_depth: int,
    ) -> None:

        self.executor = executor

        self.model_name = model_name
        self.context_registry = context_registry
        self.agent_state = agent_state
        self.sql_ticks = sql_ticks

        self.timezone = timezone

        self.branches_count = branches_count
        self.simulations_per_branch = simulations_per_branch
        self.max_depth = max_depth

        prompt_path = root_dir / "src" / "l3_agent" / "tot" / "prompt" / "INSTRUCTIONS.md"
        tot_instructions = (
            prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""
        )

        self.system_prompt = f"{tot_instructions}".strip()

    async def generate(
        self,
        event_name: str,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        task_description: str = "",
    ) -> Optional[str]:
        """
        Generates a Markdown block describing simulated thoughts branches.
        """

        log = f"[Tree of Thoughts] Initiated thoughts tree generation (Model: {self.model_name})."
        tot_logger.info(log)

        context = await self._build_filtered_context(event_name, payload, missed_events)

        target_focus = (
            task_description
            if task_description
            else "Perform a strategic analysis of the current situation and suggest optimal paths."
        )

        full_context = f"""
{context}

# CURRENT TASK 
{target_focus}

# DIRECTIVE
1. You are advised to simulate approximately {self.branches_count} macro-strategies.
2. The recommended nested simulation depth is: {self.max_depth}.
3. Branch scenarios dynamically: averaging {self.simulations_per_branch} sub-paths per node.
4. The pros and cons fields are optional but recommended for Cost-Benefit analysis.
        """.strip()

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": full_context},
        ]

        await asyncio.to_thread(self._dump_context_to_file, messages)

        raw_json = await self.executor.execute(
            model_name=self.model_name,
            messages=messages,
            temperature=0.7,
            logger=tot_logger,
            log_prefix="[Tree of Thoughts LLM]",
            tools=TOT_SCHEMA,
            tool_choice={"type": "function", "function": {"name": "submit_tree"}},
        )
        if not raw_json:
            return None
        
        stripped = raw_json.strip()
        if not stripped.startswith("{"):
            tot_logger.warning(f"[Tree of Thoughts] Invalid JSON response: {raw_json}")
            return None

        try:
            parsed = TreeResponse.model_validate_json(stripped)
            return self._format_markdown(parsed)

        except Exception as e:
            log = f"[Tree of Thoughts] Tree of Thoughts parsing error: {e}"
            tot_logger.error(log)

            return None

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    async def _build_filtered_context(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
    ) -> str:
        allowed_sections = {
            ContextSection.AGENT_STATE,
            ContextSection.DRIVES,
            ContextSection.TRAITS,
            ContextSection.MENTAL_STATES,
            ContextSection.TASKS,
            ContextSection.RAG_MEMORIES,
            ContextSection.HEARTBEAT,
        }

        all_blocks = await self.context_registry.gather_all(
            event_name=event_name,
            payload=payload,
            missed_events=missed_events,
            agent_state=self.agent_state,
        )

        filtered_blocks = []
        sorted_names = sorted(
            self.context_registry._providers.keys(),
            key=lambda k: self.context_registry._providers[k]["section"].value,
        )

        for name in sorted_names:
            section = self.context_registry._providers[name]["section"]
            if section in allowed_sections and name in all_blocks:
                filtered_blocks.append(all_blocks[name])

        # Inject raw action logs (Raw Ticks) for detailed historical awareness
        ticks_block = await self.sql_ticks.get_full_context_block(limit=10)
        filtered_blocks.insert(-1, ticks_block)

        return "\n\n\n".join(filtered_blocks).strip()

    def _format_markdown(self, tree: TreeResponse) -> str:
        """
        Converts a recursive TreeResponse object into an ASCII tree structure.
        """

        if not tree.branches:
            return ""

        step = self.agent_state.current_step
        lines = [
            "## TREE OF THOUGHTS",
            "Subconscious simulation of strategic branches for deep analysis and planning.",
            f"Generation time: Step {step}\n\n```text",
        ]

        def _render_branch(
            branch: ThoughtBranch, depth: int, prefix: str, is_last: bool, indent_prefix: str
        ):
            connector = "└── " if is_last else "├── "

            if depth == 0:
                node_title = f'No.{prefix}: "{branch.name}"'
            elif depth == 1:
                node_title = f"No.{prefix}: {branch.name}"
            else:
                node_title = f"{prefix}: {branch.name}"

            if branch.description and branch.description != branch.name:
                node_title += f" -> {branch.description}"

            lines.append(f"{indent_prefix}{connector}{node_title}")

            child_indent = indent_prefix + ("    " if is_last else "│   ")

            if branch.pros:
                pros_str = " ".join(f"[+] {p}" for p in branch.pros)
                lines.append(f"{child_indent}* Pros: {pros_str}")

            if branch.cons:
                cons_str = " ".join(f"[-] {c}" for c in branch.cons)
                lines.append(f"{child_indent}* Cons: {cons_str}")

            if branch.sub_branches:
                total_subs = len(branch.sub_branches)
                for idx, sub in enumerate(branch.sub_branches):
                    new_prefix = f"{prefix}.{idx + 1}"
                    is_sub_last = idx == total_subs - 1
                    _render_branch(sub, depth + 1, new_prefix, is_sub_last, child_indent)

        total_branches = len(tree.branches)
        for i, branch in enumerate(tree.branches):
            is_last = i == total_branches - 1
            _render_branch(branch, 0, str(i + 1), is_last, "")
            if not is_last:
                lines.append("│")
                lines.append("│")

        lines.append("```")
        result = "\n".join(lines).strip()
        tot_logger.info(result)
        return result

    def _dump_context_to_file(self, messages: List[Dict[str, Any]]) -> None:
        dump_prompt_to_file(
            "logs/prompts/tot_prompt.md", messages, meta_header="# TREE OF THOUGHTS DUMP"
        )

"""
Subagent Context Builder.

Assembles lightweight, highly focused system context for subagents,
including active task definitions, authorized skills, and local rolling history.
"""

from typing import List, Dict
from src.l3_agent.skills.registry import _REGISTRY
from src.l3_agent.swarm.roles import SubagentRole
from src.utils.settings import SwarmContextDepthConfig


class SwarmContextBuilder:
    """Stateless context compiler for subagents."""

    def __init__(
        self, role: SubagentRole, allowed_skills: List[str], config: SwarmContextDepthConfig
    ) -> None:
        """
        Initializes the subagent context builder.

        Args:
            role: Assigned subagent role.
            allowed_skills: List of skills authorized for this role.
            config: Context depth limits configuration.
        """
        self.role = role
        self.allowed_skills = allowed_skills + ["SubagentReport.submit_final_report"]
        self.config = config

    def build(
        self, subagent_id: str, task_description: str, history: List[Dict[str, str]]
    ) -> str:
        """
        Assembles user prompt context for the current subagent step.

        Args:
            subagent_id: Subagent process ID.
            task_description: Delegated task description.
            history: Local rolling execution history of this subagent.

        Returns:
            str: Compiled and truncated Markdown context.
        """
        # Extract documentation only for skills authorized for this role
        skills_docs = []
        for skill_name in self.allowed_skills:
            if skill_name in _REGISTRY:
                skills_docs.append(_REGISTRY[skill_name]["doc_string"])

        skills_str = "\n".join(skills_docs) if skills_docs else "No tools available."

        history_blocks = []

        # Limit total history length to fit context budget
        history = history[-self.config.max_steps :]
        total_history = len(history)

        for idx, step in enumerate(history):
            step_num = idx + 1
            # Check if the step qualifies as detailed (fresh)
            is_detailed = (total_history - idx) <= self.config.detailed_steps

            thoughts = step["thoughts"]
            actions = step["actions"]
            results = step["results"]

            # Apply limits based on step age
            if is_detailed:
                a_limit = self.config.action_max_chars
                r_limit = self.config.result_max_chars
                t_limit = 100000  # Fresh thoughts are not truncated
            else:
                a_limit = self.config.action_short_max_chars
                r_limit = self.config.result_short_max_chars
                t_limit = self.config.thoughts_short_max_chars

            def _truncate(text: str, limit: int, name: str) -> str:
                if len(text) > limit:
                    return (
                        text[:limit]
                        + f"\n... [{name} truncated by context compressor (> {limit} chars)]"
                    )
                return text

            thoughts = _truncate(thoughts, t_limit, "Thoughts")
            actions = _truncate(actions, a_limit, "Actions")
            results = _truncate(results, r_limit, "Results")

            history_blocks.append(
                f"* STEP {step_num}\n"
                f"### Thoughts:\n{thoughts}\n\n"
                f"### Actions:\n{actions}\n\n"
                f"### Results:\n{results}"
            )

        history_str = (
            "\n\n".join(history_blocks) if history_blocks else "No execution history yet."
        )

        return f"""
## SYSTEM INFO
- Your Subagent ID: {subagent_id}
- Your Role: {self.role.name.upper()}

## DELEGATED TASK
{task_description}

## AVAILABLE SKILLS
You are authorized to use strictly the following tools:
{skills_str}

## EXECUTION HISTORY
{history_str}
""".strip()

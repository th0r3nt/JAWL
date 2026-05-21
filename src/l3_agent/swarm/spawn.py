"""
Swarm Orchestrator (Swarm Manager).

Initializes background workers under strict asyncio Semaphore limits,
resolves active roles, and dynamically maps authorized skills directories.
"""

import asyncio
import uuid
import traceback
from pathlib import Path

from src.utils.logger import swarm_logger
from src.utils.settings import SwarmConfig

from src.l3_agent.llm.executor import LLMExecutor
from src.l3_agent.skills.registry import skill, SkillResult, _REGISTRY

from src.l3_agent.swarm.roles import Subagents, SubagentRole
from src.l3_agent.swarm.prompt.builder import SwarmPromptBuilder
from src.l3_agent.swarm.context.builder import SwarmContextBuilder
from src.l3_agent.swarm.loop import SubagentLoop


class SwarmManager:
    """Manager of the swarm subsystem. Spawns and manages stateless background subagents."""

    def __init__(
        self,
        executor: LLMExecutor,
        swarm_config: SwarmConfig,
        root_dir: Path,
    ) -> None:
        self.executor = executor
        self.config = swarm_config

        self.prompt_builder = SwarmPromptBuilder(root_dir)
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_workers)
        self.active_tasks: set[asyncio.Task] = set()

        self.role_skills: dict[str, list[str]] = {}
        self.active_roles: dict[str, SubagentRole] = {}

        for skill_name, data in _REGISTRY.items():
            for role_obj in data.get("swarm", []):
                if role_obj.id not in self.role_skills:
                    self.role_skills[role_obj.id] = []
                self.role_skills[role_obj.id].append(skill_name)
                self.active_roles[role_obj.id] = role_obj

        base_doc = "Delegates heavy tasks to background autonomous subagent, returns report. "

        if self.active_roles:
            roles_desc = ["Currently available subagent roles:"]
            for r_id, r_obj in self.active_roles.items():
                roles_desc.append(f"- '{r_id}' ({r_obj.name}): {r_obj.description}")
            roles_str = "\n".join(roles_desc)
        else:
            roles_str = "Warning: no subagent roles are active. Ensure required interfaces are enabled."

        if hasattr(self.spawn_subagent, "__func__"):
            self.spawn_subagent.__func__.__doc__ = f"{base_doc}\n\n{roles_str}"
        else:
            self.spawn_subagent.__doc__ = f"{base_doc}\n\n{roles_str}"

    @skill()
    async def spawn_subagent(self, role: str, task_description: str) -> SkillResult:
        """
        Spawns a background subagent worker for the delegated task.
        """

        if not self.config.enabled:
            return SkillResult.fail("Error: Swarm subsystem is disabled in the configuration.")

        if self.config.subagent_model == "unknown":
            return SkillResult.fail("Error: No subagent model specified in the configuration.")

        target_role = Subagents.get_by_id(role)
        if not target_role or target_role.id not in self.active_roles:
            active_ids = list(self.active_roles.keys())
            return SkillResult.fail(
                f"Role '{role}' is currently unavailable. Active roles: {active_ids}"
            )

        subagent_id = str(uuid.uuid4())[:8]

        task = asyncio.create_task(
            self._run_subagent_task(subagent_id, target_role, task_description)
        )
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

        return SkillResult.ok(
            f"Subagent {role}_{subagent_id} successfully spawned in the background. You will receive a notification upon completion."
        )

    async def _run_subagent_task(
        self, subagent_id: str, role: SubagentRole, task_description: str
    ) -> None:
        """
        Background task thread. Runs the subagent ReAct loop under semaphore limits.
        """

        try:
            actual_skills = self.role_skills.get(role.id, [])

            async with self.semaphore:
                context_builder = SwarmContextBuilder(
                    role=role, allowed_skills=actual_skills, config=self.config.context_depth
                )

                loop = SubagentLoop(
                    subagent_id=subagent_id,
                    role=role,
                    task_description=task_description,
                    executor=self.executor,
                    model_name=self.config.subagent_model,
                    prompt_builder=self.prompt_builder,
                    context_builder=context_builder,
                    allowed_skills=actual_skills,
                    max_steps=self.config.context_depth.max_steps,
                )

                await loop.run()
        except Exception:
            log = f"[Swarm] Critical exception in background subagent task {role.id}_{subagent_id}:\n{traceback.format_exc()}"
            swarm_logger.error(log)

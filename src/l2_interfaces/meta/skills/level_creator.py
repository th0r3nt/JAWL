"""
Self-expansion skills (Access Level 3: CREATOR).

God level. Allows the agent to dynamically inject its own Python scripts,
written in the sandbox, as native framework tools (Dynamic Skill Injection).
Also allows drawing custom dashboards.
"""

from typing import Dict

from src.utils.event.registry import Events

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.skills.custom import CustomSkillsRegistry


class MetaCreator:
    """Level 3 (CREATOR). Registration of agent scripts as native skills."""

    def __init__(self, meta_client: MetaClient, registry: CustomSkillsRegistry) -> None:
        self.client = meta_client
        self.registry = registry

    @skill()
    async def register_custom_skill(
        self,
        skill_name: str,
        description: str,
        filepath: str,
        func_name: str,
        parameters_dict: Dict[str, str],
    ) -> SkillResult:
        """
        Compiles proxy wrapper for sandbox function and injects it as native tool.

        skill_name: Desired callable name.
        filepath: Relative sandbox path.
        func_name: Target function name.
        parameters_dict: JSON schema args.
        """

        success, result_or_err = self.registry.register_skill(
            skill_name, description, filepath, func_name, parameters_dict
        )

        if success:
            return SkillResult.ok(
                f"Custom skill '{result_or_err}' successfully registered and is now available for execution."
            )
        return SkillResult.fail(f"Error registering skill: {result_or_err}")

    @skill()
    async def remove_custom_skill(self, skill_name: str) -> SkillResult:
        """
        Removes previously created custom skill by full name.
        """
        success, err = self.registry.unregister_skill(skill_name)

        if success:
            return SkillResult.ok(
                f"Skill '{skill_name}' successfully removed from the system."
            )
        return SkillResult.fail(f"Error removing skill: {err}")

    @skill()
    async def get_custom_skills(self) -> SkillResult:
        """
        Returns list of all registered custom skills and their mappings.
        """

        skills = self.registry.get_all_skills()
        if not skills:
            return SkillResult.ok("Custom skills list is empty.")

        lines = ["Registered integrations:"]
        for s_name, info in skills.items():
            params_str = ", ".join([f"{k}: {v}" for k, v in info.get("params", {}).items()])
            lines.append(
                f"- {s_name} | File: {info['filepath']}::{info['func_name']} | Parameters: {{{params_str}}}"
            )

        return SkillResult.ok("\n".join(lines))

    @skill()
    async def set_dashboard_block(self, name: str, markdown_content: str) -> SkillResult:
        """
        Injects static Markdown block into system context.

        name: Unique dashboard title.
        markdown_content: Block content.
        """

        await self.client.bus.publish(
            Events.SYSTEM_DASHBOARD_UPDATE, name=name, content=markdown_content
        )
        return SkillResult.ok(f"Dashboard '{name}' successfully updated.")

    @skill()
    async def remove_dashboard_block(self, name: str) -> SkillResult:
        """
        Removes custom block from system context.
        """

        await self.client.bus.publish(Events.SYSTEM_DASHBOARD_UPDATE, name=name, content="")
        return SkillResult.ok(f"Dashboard '{name}' deleted.")

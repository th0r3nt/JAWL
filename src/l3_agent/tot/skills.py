"""
Skills for manual invocation of the Tree of Thoughts simulator.
"""

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.tot.generator import ToTGenerator


class DeepThinkSkill:
    def __init__(self, generator: ToTGenerator) -> None:
        self.generator = generator

    @skill()
    async def deep_think(self, task_description: str = "") -> SkillResult:
        """
        Triggers subconscious Tree of Thoughts generation.
        Simulates future scenarios, generates macro/micro strategies.

        task_description: Optional problem description to ponder.
        """

        tree_md = await self.generator.generate(
            event_name="DEEP_THINK_REQUEST",
            payload={"task": task_description},
            missed_events=[],
            task_description=task_description,
        )

        if tree_md:
            self.generator.agent_state.current_thoughts_tree = tree_md
            return SkillResult.ok(
                "Thoughts tree successfully simulated and integrated into the system prompt."
            )
        else:
            return SkillResult.fail("Failed to generate the thoughts tree.")

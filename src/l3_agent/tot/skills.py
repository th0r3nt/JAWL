"""
Навык ручного вызова подсознания (Tree of Thoughts).
Позволяет агенту запросить генерацию стратегических веток в любой момент.
"""

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.tot.generator import ToTGenerator


class DeepThinkSkill:
    def __init__(self, generator: ToTGenerator) -> None:
        self.generator = generator

    @skill()
    async def deep_think(self, task_description: str = "") -> SkillResult:
        """
        Обращается к подсознанию для генерации вложенного "Дерева мыслей" (Tree of Thoughts).

        Симулирует в уме несколько вариантов развития событий будущего, 
        генерируя макро- и микро- стратегии, анализируя плюсы и минусы каждого пути.

        Рекомендуется применять, если нужно выполнить важное действие, 
        сделать план, составить мозговой штурм или провести сложный анализ.

        Args:
            task_description: (опционально) Описание проблемы или задачи, о которой подсознанию нужно подумать.
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
                "Дерево мыслей успешно сгенерировано и интегрировано в системный промпт. "
            )
        else:
            return SkillResult.fail(
                "Не удалось сгенерировать дерево мыслей."
            )

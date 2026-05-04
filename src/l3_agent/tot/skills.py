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
    async def deep_think(self) -> SkillResult:
        """
        Обращается к подсознанию для генерации "Дерева мыслей" (Tree of Thoughts).
        Рекомендуется применять, если нужно выполнить критически важное/опасное действие,
        сгенерировать план или составить мозговой штурм.

        Подсознание проанализирует контекст и сгенерирует несколько стратегических путей (веток).
        """

        # Передаем заглушку триггера, так как генератор сам подтянет свежие логи из БД
        tree_md = await self.generator.generate(
            event_name="DEEP_THINK_REQUEST", payload={}, missed_events=[]
        )

        if tree_md:
            self.generator.agent_state.current_thoughts_tree = tree_md
            return SkillResult.ok(
                "Дерево мыслей успешно сгенерировано. "
            )
        else:
            return SkillResult.fail(
                "Не удалось сгенерировать дерево мыслей (ошибка API или парсинга)."
            )

"""
Навыки для ручного извлечения информации из гибридной памяти (Vector-Graph RAG).
Доступны исключительно главному агенту-оркестратору.
"""

from typing import List

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.context.rag.orchestrator import GraphRAGOrchestrator


class MemoryRecallSkill:
    """Навык для ручного глубокого поиска в векторно-графовой памяти."""

    def __init__(self, orchestrator: GraphRAGOrchestrator) -> None:
        """
        Инициализирует навык работы с памятью.

        Args:
            orchestrator: Ядро гибридного поиска (Vector-Graph RAG).
        """
        self.orchestrator = orchestrator

    @skill()
    async def recall_information(self, queries: List[str]) -> SkillResult:
        """
        Выполняет глубокий гибридный поиск (Vector-Graph RAG) по внутренней базе знаний, мыслей и связей агента.

        Алгоритм автоматически извлечет ключевые слова, найдет сущности в графе и подтянет
        ассоциативные воспоминания.

        Args:
            queries: Массив текстовых запросов или ключевых слов.
        """
        if not queries:
            return SkillResult.fail("Ошибка: Массив запросов не может быть пустым.")

        # Очищаем массив от пустых строк
        clean_queries = [q.strip() for q in queries if q and q.strip()]

        if not clean_queries:
            return SkillResult.fail("Ошибка: Все переданные запросы оказались пустыми.")

        # Оркестратор RAG изначально спроектирован для приема массивов строк
        result_md = await self.orchestrator.run(clean_queries)

        if not result_md:
            return SkillResult.ok(
                f"По запросам {clean_queries} в памяти не найдено релевантной информации."
            )

        # Возвращаем сформированный Markdown блок с результатами из вектора и графа
        return SkillResult.ok(f"Результаты поиска в памяти:\n\n{result_md}")

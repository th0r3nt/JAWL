"""
Skills for manual retrieval of information from hybrid memory (Vector-Graph RAG).
Available only for the main agent-orchestrator.
"""

from typing import List

from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.context.rag.orchestrator import GraphRAGOrchestrator


class MemoryRecallSkill:
    """Skill for manual deep search in vector-graph memory."""

    def __init__(self, orchestrator: GraphRAGOrchestrator) -> None:
        """
        Initializes memory recall tool.

        Args:
            orchestrator: Vector-Graph RAG orchestrator core.
        """
        self.orchestrator = orchestrator

    @skill()
    async def recall_information(self, queries: List[str]) -> SkillResult:
        """
        Searches internal knowledge, thoughts, and relation database.
        """

        if not queries:
            return SkillResult.fail("Error: Queries list cannot be empty.")

        clean_queries = [q.strip() for q in queries if q and q.strip()]

        if not clean_queries:
            return SkillResult.fail("Error: All passed queries are empty.")

        result_md = await self.orchestrator.run(clean_queries)

        if not result_md:
            return SkillResult.ok(
                f"No relevant information found in memory for queries: {clean_queries}."
            )

        return SkillResult.ok(f"Memory recall results:\n\n{result_md}")

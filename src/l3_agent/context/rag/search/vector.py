"""
Semantic Database Search Wrapper (Vector Search).

Provides unified semantic query interface. Queries 'knowledge' and 'thoughts'
collections concurrently, handling deduping and score prioritization.
"""

import asyncio
from typing import List, Dict, Any

from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts


class VectorSearchWrapper:
    """Wrapper over vector databases."""

    def __init__(
        self,
        vector_knowledge: VectorKnowledge,
        vector_thoughts: VectorThoughts,
        top_k: int = 5,
    ) -> None:
        """
        Args:
            vector_knowledge: Knowledge base controller.
            vector_thoughts: Thoughts controller.
            top_k: Max returned records count per single search vector.
        """
        self.vector_knowledge = vector_knowledge
        self.vector_thoughts = vector_thoughts
        self.top_k = top_k

    async def search_batch(self, query_vectors: List[List[float]]) -> List[Dict[str, Any]]:
        """
        Executes parallel semantic search over an embedding array.
        Queries both collections concurrently, merges, and dedupes outputs.

        Args:
            query_vectors: List of vectorized embeddings.

        Returns:
            List[Dict[str, Any]]: List of unique matched records.
        """

        if not query_vectors:
            return []

        tasks = []
        for vector in query_vectors:
            if self.vector_knowledge.db.client:
                tasks.append(
                    self.vector_knowledge.db.client.query_points(
                        collection_name=self.vector_knowledge.collection.name,
                        query=vector,
                        limit=self.top_k,
                        score_threshold=self.vector_knowledge.similarity_threshold,
                        with_payload=True,
                    )
                )

            if self.vector_thoughts.db.client:
                tasks.append(
                    self.vector_thoughts.db.client.query_points(
                        collection_name=self.vector_thoughts.collection.name,
                        query=vector,
                        limit=self.top_k,
                        score_threshold=self.vector_thoughts.similarity_threshold,
                        with_payload=True,
                    )
                )

        results_matrix = await asyncio.gather(*tasks, return_exceptions=True)

        unique_points: Dict[str, Dict[str, Any]] = {}

        for i, search_result in enumerate(results_matrix):
            if isinstance(search_result, Exception) or not search_result:
                continue

            collection_name = "knowledge" if i % 2 == 0 else "thoughts"

            points = (
                search_result.points if hasattr(search_result, "points") else search_result
            )

            for point in points:
                point_id = str(point.id)
                score = float(point.score)
                text = point.payload.get("text", "")

                if point_id in unique_points:
                    if score > unique_points[point_id]["score"]:
                        unique_points[point_id]["score"] = score
                        unique_points[point_id]["collection"] = collection_name
                        unique_points[point_id]["text"] = text
                        unique_points[point_id]["tags"] = point.payload.get("tags", [])
                        unique_points[point_id]["source"] = point.payload.get(
                            "source", "Internal monologue"
                        )
                        unique_points[point_id]["reliability"] = point.payload.get(
                            "reliability", "assumption"
                        )
                else:
                    unique_points[point_id] = {
                        "id": point_id,
                        "text": text,
                        "score": score,
                        "collection": collection_name,
                        "tags": point.payload.get("tags", []),
                        "source": point.payload.get("source", "Internal monologue"),
                        "reliability": point.payload.get("reliability", "assumption"),
                    }

        return list(unique_points.values())

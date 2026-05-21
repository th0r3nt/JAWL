"""
CRUD controller for the 'code_ast' collection.

Stores docstrings and descriptions of functions, classes, and files for the Code Graph.
"""

import uuid
from typing import TYPE_CHECKING, List, Dict, Any
from qdrant_client import models

from src.utils.logger import main_logger

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.embedding import EmbeddingModel
    from src.l1_databases.vector.collections import VectorCollection


class VectorCodeAST:
    """
    Vector memory controller for storing docstrings and code snippets.
    """

    def __init__(
        self,
        db: "VectorDB",
        embedding_model: "EmbeddingModel",
        collection: "VectorCollection",
        similarity_threshold: float = 0.65,
    ) -> None:
        self.db = db
        self.collection = collection
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold

    async def save_doc(self, node_id: str, text: str, project_id: str, node_type: str) -> None:
        """
        Vectorizes the class/function docstring.
        """

        if not text.strip() or not self.db.client:
            return

        vector = await self.embedding_model.get_embedding(text)

        # Use a predictable ID to prevent duplicate generation during re-indexing
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, node_id))

        payload = {
            "node_id": node_id,
            "project_id": project_id,
            "type": node_type,
            "text": text,
        }

        await self.db.client.upsert(
            collection_name=self.collection.name,
            points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    async def search(
        self, query: str, project_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across docstrings within the specified project.
        """
        if not self.db.client:
            return []

        query_vector = await self.embedding_model.get_embedding(query)
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="project_id", match=models.MatchValue(value=project_id)
                )
            ]
        )

        search_result = await self.db.client.query_points(
            collection_name=self.collection.name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=self.similarity_threshold,
            with_payload=True,
        )

        # Support backward compatibility and mocks in tests
        points = search_result.points if hasattr(search_result, "points") else search_result

        return [
            {
                "score": res.score,
                "node_id": res.payload.get("node_id"),
                "type": res.payload.get("type"),
                "text": res.payload.get("text"),
            }
            for res in points
        ]

    async def delete_project(self, project_id: str) -> None:
        """
        Deletes all vectors belonging to a specific project.
        """

        if not self.db.client:
            return

        await self.db.client.delete(
            collection_name=self.collection.name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="project_id", match=models.MatchValue(value=project_id)
                        )
                    ]
                )
            ),
        )
        main_logger.info(f"[Vector DB] AST project '{project_id}' vectors deleted.")

"""
CRUD-контроллер для коллекции 'code_ast'.

Хранит докстринги и описания функций, классов и файлов для Code Graph.
"""

import uuid
from typing import TYPE_CHECKING, List, Dict, Any
from qdrant_client import models

from src.utils.logger import system_logger

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.embedding import EmbeddingModel
    from src.l1_databases.vector.collections import VectorCollection


class VectorCodeAST:
    """
    Контроллер векторной памяти для хранения докстрингов и кусков кода.
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
        Векторизует докстринг класса/функции.
        """

        if not text.strip() or not self.db.client:
            return

        vector = await self.embedding_model.get_embedding(text)

        # Используем предсказуемый ID, чтобы не плодить дубликаты при переиндексации
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
        Семантический поиск по докстрингам внутри указанного проекта.
        """

        if not self.db.client:
            return []

        query_vector = await self.embedding_model.get_embedding(query)

        # Фильтруем строго по проекту
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="project_id", match=models.MatchValue(value=project_id)
                )
            ]
        )

        results = await self.db.client.search(
            collection_name=self.collection.name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=self.similarity_threshold,
            with_payload=True,
        )

        return [
            {
                "score": res.score,
                "node_id": res.payload.get("node_id"),
                "type": res.payload.get("type"),
                "text": res.payload.get("text"),
            }
            for res in results
        ]

    async def delete_project(self, project_id: str) -> None:
        """
        Удаляет все вектора, принадлежащие конкретному проекту.
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
        system_logger.info(f"[Vector DB] Вектора проекта AST '{project_id}' удалены.")

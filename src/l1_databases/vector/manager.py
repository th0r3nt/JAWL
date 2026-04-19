from pathlib import Path

from src.l1_databases.vector.db import VectorDB
from src.l1_databases.vector.embedding import EmbeddingModel
from src.l1_databases.vector.collections import VectorCollection
from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts


class VectorManager:
    """
    Фасад для векторного слоя.
    Инкапсулирует инициализацию клиента Qdrant, модели FastEmbed и CRUD-обработчиков.
    """

    def __init__(
        self,
        db_path: Path,
        embedding_model_path: Path,
        embedding_model_name: str,
        vector_size: int = 384,
        similarity_threshold: float = 0.43,
        timezone: int = 0,
    ):
        self.collection_name_knowledge = "knowledge"
        self.collection_name_thoughts = "thoughts"

        self.db = VectorDB(
            db_path=str(db_path),
            collections=[self.collection_name_knowledge, self.collection_name_thoughts],
            vector_size=vector_size,
        )
        self.embedding = EmbeddingModel(
            model_path=str(embedding_model_path), model_name=embedding_model_name
        )

        knowledge_col = VectorCollection(self.db, self.collection_name_knowledge)
        thoughts_col = VectorCollection(self.db, self.collection_name_thoughts)

        # Передаем timezone в CRUD-обработчики
        self.knowledge = VectorKnowledge(
            db=self.db,
            collection=knowledge_col,
            embedding_model=self.embedding,
            similarity_threshold=similarity_threshold,
            timezone=timezone,
        )
        self.thoughts = VectorThoughts(
            db=self.db,
            collection=thoughts_col,
            embedding_model=self.embedding,
            similarity_threshold=similarity_threshold,
            timezone=timezone,
        )

    async def connect(self) -> None:
        await self.db.connect()

    async def disconnect(self) -> None:
        await self.db.disconnect()

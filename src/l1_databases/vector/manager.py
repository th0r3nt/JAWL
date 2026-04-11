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
    ):

        # Названия коллекций
        self.knowledge = "knowledge"
        self.thoughts = "thoughts"

        # Базовые компоненты
        self.db = VectorDB(
            db_path=str(db_path),
            collections=[self.knowledge, self.thoughts],
            vector_size=vector_size,
        )
        self.embedding = EmbeddingModel(
            model_path=str(embedding_model_path), model_name=embedding_model_name
        )

        # Обертки коллекций
        knowledge_col = VectorCollection(self.db, self.knowledge)
        thoughts_col = VectorCollection(self.db, self.thoughts)

        # CRUD-интерфейсы (скиллы агента)
        self.knowledge = VectorKnowledge(
            db=self.db, collection=knowledge_col, embedding_model=self.embedding
        )
        self.thoughts = VectorThoughts(
            db=self.db, collection=thoughts_col, embedding_model=self.embedding
        )

    async def connect(self):
        """Пробрасывает асинхронное подключение к Qdrant."""
        await self.db.connect()

    async def disconnect(self):
        """Корректно закрывает соединения."""
        await self.db.disconnect()

"""
Фасад для слоя семантической векторной памяти.

Оркестрирует запуск Qdrant клиента, загрузку ONNX Embedding-модели
и сборку CRUD-контроллеров для знаний и мыслей.
"""

from pathlib import Path

from src.l1_databases.vector.db import VectorDB
from src.l1_databases.vector.embedding import EmbeddingModel
from src.l1_databases.vector.collections import VectorCollection
from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts


class VectorManager:
    """
    Фасад для векторного слоя памяти.
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
    ) -> None:
        """
        Инициализирует фасад векторной БД.

        Args:
            db_path: Путь к хранилищу Qdrant.
            embedding_model_path: Путь к кэшу моделей FastEmbed.
            embedding_model_name: Название модели (напр. 'intfloat/multilingual-e5-large').
            vector_size: Размерность вектора.
            similarity_threshold: Порог косинусного сходства для отсева нерелевантного шума.
            timezone: Смещение часового пояса.
        """
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
        """Открывает подключение к Qdrant и создает структуры данных."""
        await self.db.connect()

    async def disconnect(self) -> None:
        """Безопасно закрывает подключение к Qdrant."""
        await self.db.disconnect()

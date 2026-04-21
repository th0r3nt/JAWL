import os
import pytest
import pytest_asyncio

from src.l1_databases.vector.db import VectorDB
from src.l1_databases.vector.collections import VectorCollection
from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts


class MockEmbeddingModel:
    """
    Легковесная заглушка модели для тестов.
    Генерирует простые 3D вектора для проверки логики косинусного расстояния в Qdrant
    без необходимости грузить тяжелые ONNX-модели.
    """

    def __init__(self):
        self.model_name = "mock-model"
        self.model_path = "/dev/null"

    async def get_embedding(self, text: str) -> list[float]:
        text_lower = text.lower()
        # Создаем ортогональные вектора для четкого семантического разделения
        if "яблоко" in text_lower or "фрукт" in text_lower:
            return [1.0, 0.0, 0.0]

        elif "машина" in text_lower or "двигатель" in text_lower:
            return [0.0, 1.0, 0.0]

        else:
            # Дефолтный вектор для всего остального ("шум")
            return [0.0, 0.0, 1.0]


@pytest_asyncio.fixture
async def vector_db(tmp_path):
    """Поднимает чистую локальную Qdrant БД во временной папке для каждого теста."""
    db_path = os.path.join(tmp_path, "test_qdrant_db")
    # Используем размер вектора = 3, т.к. наша Mock-модель выдает списки из 3 элементов
    db = VectorDB(db_path=db_path, collections=["knowledge", "thoughts"], vector_size=3)

    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
def mock_embedding():
    return MockEmbeddingModel()


@pytest.fixture
def knowledge_manager(vector_db, mock_embedding):
    collection = VectorCollection(db=vector_db, collection_name="knowledge")
    return VectorKnowledge(
        db=vector_db,
        collection=collection,
        embedding_model=mock_embedding,
        similarity_threshold=0.5,
    )


@pytest.fixture
def thoughts_manager(vector_db, mock_embedding):
    collection = VectorCollection(db=vector_db, collection_name="thoughts")
    return VectorThoughts(
        db=vector_db,
        collection=collection,
        embedding_model=mock_embedding,
        similarity_threshold=0.5,
    )

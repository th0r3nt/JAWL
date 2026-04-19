import os
import re
import pytest
import pytest_asyncio

from unittest.mock import MagicMock, patch

from src.l1_databases.vector.db import VectorDB
from src.l1_databases.vector.collections import VectorCollection
from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts


# ===================================================================
# MOCKS
# ===================================================================


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


# ===================================================================
# FIXTURES
# ===================================================================


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


# ===================================================================
# ХЕЛПЕРЫ
# ===================================================================


def extract_id(log_msg: str) -> str:
    """Вытаскивает UUID из текстового ответа агента."""
    match = re.search(r"ID:\s([a-f0-9\-]+)", log_msg)
    if match:
        return match.group(1)
    raise ValueError(f"Не удалось найти ID в строке: {log_msg}")


# ===================================================================
# TESTS: CORE
# ===================================================================


@pytest.mark.asyncio
async def test_db_initialization(tmp_path):
    """Тест: проверяем создание БД и её коллекций на диске."""
    db_path = os.path.join(tmp_path, "init_db")
    db = VectorDB(db_path=db_path, collections=["test_col"], vector_size=3)

    await db.connect()
    assert os.path.exists(db_path)

    # Проверяем, что коллекция реально создалась в Qdrant
    assert await db.client.collection_exists("test_col") is True

    await db.disconnect()
    assert db.client is None


# ===================================================================
# TESTS: KNOWLEDGE
# ===================================================================


@pytest.mark.asyncio
async def test_knowledge_save_and_search(knowledge_manager):
    """Тест: сохранение факта и его успешный семантический поиск."""

    # Сохраняем два совершенно разных знания
    res1 = await knowledge_manager.save_knowledge("Боги смерти едят яблоки")
    res2 = await knowledge_manager.save_knowledge("Машина имеет мощный двигатель")

    assert res1.is_success
    assert res2.is_success

    # Ищем информацию про яблоки
    search_result = await knowledge_manager.search_knowledge("Расскажи про яблоки")

    assert search_result.is_success
    assert "яблоки" in search_result.message
    assert "Машина" not in search_result.message


@pytest.mark.asyncio
async def test_knowledge_search_not_found(knowledge_manager):
    """Тест: поиск того, чего нет, не должен ломать систему."""
    # Сохраняем "яблоко", а ищем "шум" (другой вектор)
    await knowledge_manager.save_knowledge("Яблоко")

    search_result = await knowledge_manager.search_knowledge("Неизвестный космос")

    assert search_result.is_success
    assert "не дал результатов" in search_result.message


@pytest.mark.asyncio
async def test_knowledge_delete(knowledge_manager):
    """Тест: удаление знания по ID."""

    # Сохраняем и вытаскиваем ID из строки возврата
    save_result = await knowledge_manager.save_knowledge("Временный факт")
    assert save_result.is_success

    point_id = extract_id(save_result.message)

    # Проверяем, что оно там есть
    all_k = await knowledge_manager.get_all_knowledge()
    assert "Временный факт" in all_k.message

    # Удаляем
    del_result = await knowledge_manager.delete_knowledge(point_id)
    assert del_result.is_success

    # Проверяем, что пусто
    all_k_after = await knowledge_manager.get_all_knowledge()
    assert "пуста" in all_k_after.message


@pytest.mark.asyncio
async def test_knowledge_get_all(knowledge_manager):
    """Тест: чтение массива без семантики (с учетом лимита)."""

    await knowledge_manager.save_knowledge("Факт 1")
    await knowledge_manager.save_knowledge("Факт 2")
    await knowledge_manager.save_knowledge("Факт 3")

    # Вытаскиваем с лимитом 2
    result = await knowledge_manager.get_all_knowledge(limit=2)
    assert result.is_success

    # Qdrant может возвращать в разном порядке при scroll,
    # просто убедимся, что вернулось 2 записи (считаем количество подстрок 'ID:')
    count_ids = result.message.count("[ID:")
    assert count_ids == 2


# ===================================================================
# TESTS: THOUGHTS
# ===================================================================


@pytest.mark.asyncio
async def test_thoughts_save_and_search(thoughts_manager):
    """Тест: сохранение мыслей (рефлексии) агента."""

    save_result = await thoughts_manager.save_thought("Я подумал про яблоко")
    assert save_result.is_success

    # Ищем по теме
    search_result = await thoughts_manager.search_thoughts("Что я думал про фрукт?")

    assert search_result.is_success
    assert "Я подумал про яблоко" in search_result.message


@pytest.mark.asyncio
async def test_thoughts_empty_db(thoughts_manager):
    """Тест: чтение из пустой базы мыслей."""
    result = await thoughts_manager.get_all_thoughts()
    assert result.is_success
    assert "пуста" in result.message


# ===================================================================
# TESTS: EMBEDDING WRAPPER
# ===================================================================


@pytest.mark.asyncio
@patch("src.l1_databases.vector.embedding.TextEmbedding")
async def test_embedding_model_wrapper(mock_fastembed):
    """Тест: EmbeddingModel корректно вызывает генератор fastembed и возвращает list."""
    from src.l1_databases.vector.embedding import EmbeddingModel
    import numpy as np

    # Настраиваем мок так, чтобы он возвращал генератор с одним numpy array (как в реальности)
    mock_instance = MagicMock()
    mock_instance.embed.return_value = iter([np.array([0.1, 0.2, 0.3])])
    mock_fastembed.return_value = mock_instance

    # Инициализируем модель (fastembed не будет качаться, так как он замокан)
    model = EmbeddingModel(model_path="/fake", model_name="fake-model")

    # Запрашиваем вектор
    vector = await model.get_embedding("Тестовый текст")

    # Проверяем, что это list из float (а не numpy array или генератор)
    assert isinstance(vector, list)
    assert vector == [0.1, 0.2, 0.3]
    mock_instance.embed.assert_called_once_with("Тестовый текст")

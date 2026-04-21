import os
import pytest
from unittest.mock import MagicMock, patch
from src.l1_databases.vector.db import VectorDB


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

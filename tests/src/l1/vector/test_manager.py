import pytest
from unittest.mock import patch, AsyncMock
from src.l1_databases.vector.manager import VectorManager



@pytest.mark.asyncio
@patch("src.l1_databases.vector.manager.VectorDB")
@patch("src.l1_databases.vector.manager.EmbeddingModel")
async def test_vector_manager_lifecycle(mock_emb, mock_db, tmp_path):
    """Тест: VectorManager инициализирует Qdrant, эмбеддинги и CRUD."""

    # Мокаем асинхронные методы мокнутого VectorDB
    mock_db.return_value.connect = AsyncMock()
    mock_db.return_value.disconnect = AsyncMock()

    manager = VectorManager(
        db_path=tmp_path / "qdrant",
        embedding_model_path=tmp_path / "models",
        embedding_model_name="mock-model",
    )

    assert manager.knowledge is not None
    assert manager.thoughts is not None

    await manager.connect()
    mock_db.return_value.connect.assert_awaited_once()

    await manager.disconnect()
    mock_db.return_value.disconnect.assert_awaited_once()

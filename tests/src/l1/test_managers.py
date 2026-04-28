import pytest
from unittest.mock import patch, AsyncMock

from src.l1_databases.sql.db import SQLDB
from src.l1_databases.sql.manager import SQLManager
from src.l1_databases.vector.manager import VectorManager


@pytest.mark.asyncio
async def test_sqldb_lifecycle(tmp_path):
    """Тест: SQLDB корректно создает и закрывает SQLite подключения."""
    db_path = tmp_path / "test.db"
    db = SQLDB(str(db_path))

    await db.connect()
    assert db_path.exists()  # База создалась физически

    await db.disconnect()


@pytest.mark.asyncio
@patch("src.l1_databases.sql.manager.SQLDrives.bootstrap_fundamental_drives")
async def test_sql_manager_lifecycle(mock_bootstrap, tmp_path):
    """Тест: SQLManager инициализирует все CRUD модули и вызывает загрузку драйвов."""
    db_path = tmp_path / "test.db"
    manager = SQLManager(db_path=db_path)

    # Проверяем, что все под-модули создались
    assert manager.tasks is not None
    assert manager.ticks is not None
    assert manager.mental_states is not None
    assert manager.personality_traits is not None
    assert manager.drives is not None

    await manager.connect()
    mock_bootstrap.assert_called_once()  # Фундаментальные мотиваторы загрузились

    await manager.disconnect()


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

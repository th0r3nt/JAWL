import pytest
from unittest.mock import patch

from src.l1_databases.sql.db import SQLDB
from src.l1_databases.sql.manager import SQLManager


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


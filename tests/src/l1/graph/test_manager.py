import pytest
from pathlib import Path
from src.l1_databases.graph.manager import GraphManager


@pytest.mark.asyncio
async def test_graph_manager_lifecycle(tmp_path: Path):
    """
    Тест: Фасад корректно инициализирует БД и CRUD.
    """
    db_path = tmp_path / "graph_mgr"
    manager = GraphManager(db_path=db_path)

    assert manager.db is not None
    assert manager.crud is not None

    await manager.connect()
    assert manager.db.conn is not None

    await manager.disconnect()
    assert manager.db.conn is None
import pytest
import pytest_asyncio
from pathlib import Path

from src.l1_databases.graph.manager import GraphManager


@pytest_asyncio.fixture
async def graph_manager(tmp_path: Path):
    """
    Создает изолированный инстанс GraphManager в чистой временной директории.
    Гарантирует безопасное отключение базы после завершения теста
    для освобождения файловых блокировок (File Locks) KuzuDB.
    """
    db_path = tmp_path / "test_kuzu_db"
    manager = GraphManager(db_path=db_path, max_nodes=100)
    
    await manager.connect()
    
    yield manager
    
    await manager.disconnect()
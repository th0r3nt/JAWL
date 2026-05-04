import pytest
from pathlib import Path
from src.l1_databases.graph.db import GraphDB


@pytest.mark.asyncio
async def test_graph_db_connect_creates_files(tmp_path: Path):
    """
    Тест: Подключение к БД успешно создает физические файлы и таблицы
    схемы в указанной директории.
    """
    db_path = tmp_path / "db_core"
    db = GraphDB(db_path=str(db_path))

    await db.connect()
    
    assert db_path.exists()
    assert db.db is not None
    assert db.conn is not None

    await db.disconnect()
    assert db.conn is None
    assert db.db is None


@pytest.mark.asyncio
async def test_graph_db_idempotent_schema(tmp_path: Path):
    """
    Тест: Повторный запуск _init_schema не должен крашить базу
    ошибками "Таблица уже существует" (Идемпотентность).
    """
    db_path = tmp_path / "db_idem"
    db = GraphDB(db_path=str(db_path))

    await db.connect()
    
    # Принудительно вызываем инициализацию схемы еще раз
    # Внутри должен сработать перехват RuntimeError
    db._init_schema()

    await db.disconnect()
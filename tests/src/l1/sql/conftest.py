import pytest
import pytest_asyncio

from src.l1_databases.sql.db import SQLDB
from src.l1_databases.sql.management.tasks import SQLTasks
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits
from src.l1_databases.sql.management.mental_states import SQLMentalStates
from src.l1_databases.sql.management.drives import SQLDrives


@pytest_asyncio.fixture
async def memory_db():
    """Поднимает чистую SQL БД в оперативной памяти для тестов."""
    db = SQLDB(db_path=":memory:")
    # Подменяем URL (т.к. SQLDB ожидает путь к файлу)
    db.engine = db.engine.execution_options(compiled_cache=None)
    db.engine.url = db.engine.url.set(database=":memory:")

    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
def mental_states_manager(memory_db):
    return SQLMentalStates(db=memory_db, max_entities=10)


@pytest.fixture
def ticks_manager(memory_db):
    return SQLTicks(db=memory_db)


@pytest.fixture
def tasks_manager(memory_db):
    return SQLTasks(db=memory_db, max_tasks=2)


@pytest.fixture
def traits_manager(memory_db):
    return SQLPersonalityTraits(db=memory_db, max_traits=2)


@pytest.fixture
def drives_manager(memory_db):
    # Ставим маленькие лимиты для теста
    return SQLDrives(
        db=memory_db,
        decay_rate=5.0,
        decay_interval_sec=3600,
        max_history=3,
        max_custom=2,
        tz_offset=3,
    )

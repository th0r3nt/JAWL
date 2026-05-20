import pytest
import pytest_asyncio

from src.l1_databases.sql.db import SQLDB

from src.l1_databases.sql.management.tasks.crud import SQLTasks
from src.l1_databases.sql.management.mental_states.crud import SQLMentalStates
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits
from src.l1_databases.sql.management.drives.crud import SQLDrives
from src.l1_databases.sql.management.notes import SQLNotes
from src.l1_databases.sql.management.hypotheses.crud import SQLHypotheses


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
def notes_manager(memory_db):
    return SQLNotes(db=memory_db, max_notes=2, tz_offset=3)


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
        pause_on_offline=True,
        max_history=3,
        max_custom=2,
        tz_offset=3,
        fundamental_config={
            "curiosity": {"enabled": True, "decay": {"rate": 5.0, "interval_sec": 3600}},
            "social": {"enabled": True, "decay": {"rate": 5.0, "interval_sec": 3600}},
            "mastery": {"enabled": True, "decay": {"rate": 5.0, "interval_sec": 3600}},
        },
    )


@pytest.fixture
def hypotheses_manager(memory_db):
    return SQLHypotheses(db=memory_db, max_clusters=2, max_hypotheses=4, tz_offset=3)

import pytest
import pytest_asyncio
import asyncio

from src.l1_databases.sql.db import SQLDB

# CRUD классы
from src.l1_databases.sql.management.tasks import SQLTasks
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits

# ===================================================================
# FIXTURES
# ===================================================================


@pytest_asyncio.fixture
async def memory_db():
    """Поднимает чистую SQL БД в оперативной памяти для тестов."""
    # Специальный URL для aiosqlite in-memory
    db = SQLDB(db_path=":memory:")
    # Подменяем URL (т.к. SQLDB ожидает путь к файлу)
    db.engine = db.engine.execution_options(compiled_cache=None)
    db.engine.url = db.engine.url.set(database=":memory:")

    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
def tasks_manager(memory_db):
    return SQLTasks(db=memory_db)


@pytest.fixture
def ticks_manager(memory_db):
    return SQLTicks(db=memory_db)


@pytest.fixture
def traits_manager(memory_db):
    return SQLPersonalityTraits(db=memory_db)


# ===================================================================
# TESTS: TASKS
# ===================================================================


@pytest.mark.asyncio
async def test_create_and_get_tasks(tasks_manager):
    # Создаем
    res_create = await tasks_manager.create_task("Написать тесты", "Сегодня", "KISS")
    assert res_create.is_success is True
    assert "ID:" in res_create.message

    # Вытаскиваем ID
    task_id = res_create.message.split("ID: ")[1].strip()

    # Проверяем получение
    res_get = await tasks_manager.get_tasks()
    assert res_get.is_success is True
    assert "Написать тесты" in res_get.message
    assert task_id in res_get.message


@pytest.mark.asyncio
async def test_update_task(tasks_manager):
    res_create = await tasks_manager.create_task("Старая задача")
    task_id = res_create.message.split("ID: ")[1].strip()

    # Обновляем
    res_update = await tasks_manager.update_task(task_id, description="Новая задача")
    assert res_update.is_success is True

    # Проверяем, что изменилось
    res_get = await tasks_manager.get_tasks()
    assert "Новая задача" in res_get.message
    assert "Старая задача" not in res_get.message


@pytest.mark.asyncio
async def test_delete_task(tasks_manager):
    res_create = await tasks_manager.create_task("Задача на удаление")
    task_id = res_create.message.split("ID: ")[1].strip()

    # Удаляем
    res_delete = await tasks_manager.delete_task(task_id)
    assert res_delete.is_success is True

    # Проверяем, что пусто
    res_get = await tasks_manager.get_tasks()
    assert "Список задач пуст" in res_get.message


# ===================================================================
# TESTS: TICKS
# ===================================================================


@pytest.mark.asyncio
async def test_save_and_get_ticks(ticks_manager):
    # Симулируем 3 тика агента
    for i in range(3):
        await ticks_manager.save_tick(
            thoughts=f"Мысль {i}",
            actions=[{"tool_name": "test", "parameters": {}}],
            results={"test": "ok"},
        )
        await asyncio.sleep(0.01)

    # Получаем последние 2
    last_ticks = await ticks_manager.get_ticks(limit=2)

    assert len(last_ticks) == 2
    # Поскольку они возвращаются в хронологическом порядке (сначала старые, потом новые),
    # последние 2 из [0, 1, 2] — это 1 и 2.
    assert last_ticks[0].thoughts == "Мысль 1"
    assert last_ticks[1].thoughts == "Мысль 2"

    # Проверяем JSON структуру
    assert last_ticks[1].actions[0]["tool_name"] == "test"
    assert last_ticks[1].results["test"] == "ok"


# ===================================================================
# TESTS: PERSONALITY TRAITS
# ===================================================================


@pytest.mark.asyncio
async def test_add_and_get_traits(traits_manager):
    # Создаем черту
    res_add = await traits_manager.add_trait(
        name="Токсичность", description="Отвечать сарказмом на глупые вопросы", reason="Скука"
    )
    assert res_add.is_success is True
    assert "ID:" in res_add.message

    # Вытаскиваем ID
    trait_id = res_add.message.split("ID: ")[1].strip()

    # Проверяем получение
    res_get = await traits_manager.get_traits()
    assert res_get.is_success is True
    assert "Токсичность" in res_get.message
    assert "Скука" in res_get.message
    assert trait_id in res_get.message


@pytest.mark.asyncio
async def test_remove_trait(traits_manager):
    res_add = await traits_manager.add_trait("Любопытство", "Спрашивать детали")
    trait_id = res_add.message.split("ID: ")[1].strip()

    # Удаляем
    res_delete = await traits_manager.remove_trait(trait_id)
    assert res_delete.is_success is True

    # Проверяем, что список пуст
    res_get = await traits_manager.get_traits()
    assert "Список приобретенных черт личности пуст" in res_get.message

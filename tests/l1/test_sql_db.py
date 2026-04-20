import pytest
import pytest_asyncio
import asyncio

from src.l1_databases.sql.db import SQLDB

# CRUD классы
from src.l1_databases.sql.management.tasks import SQLTasks
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits
from src.l1_databases.sql.management.mental_states import SQLMentalStates
from src.l1_databases.sql.management.drives import SQLDrives

# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def mental_states_manager(memory_db):
    return SQLMentalStates(db=memory_db, max_entities=10)


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
        db=memory_db, decay_rate=5.0, decay_interval_sec=3600, max_history=3, max_custom=2, tz_offset=3
    )


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


@pytest.mark.asyncio
async def test_add_task_limit(tasks_manager):
    """Тест: лимит на количество задач соблюдается."""
    await tasks_manager.create_task("Task 1")
    await tasks_manager.create_task("Task 2")

    res_fail = await tasks_manager.create_task("Task 3")
    assert res_fail.is_success is False
    assert "Достигнут лимит" in res_fail.message


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


@pytest.mark.asyncio
async def test_add_trait_limit(traits_manager):
    await traits_manager.add_trait("Trait 1", "Desc")
    await traits_manager.add_trait("Trait 2", "Desc")

    # Третий должен упасть в лимит
    res_fail = await traits_manager.add_trait("Trait 3", "Desc")
    assert res_fail.is_success is False
    assert "Достигнут лимит" in res_fail.message


# ===================================================================
# TESTS: MENTAL STATES
# ===================================================================


@pytest.mark.asyncio
async def test_mental_states_crud(mental_states_manager):
    # Создаем
    res_create = await mental_states_manager.create_mental_state(
        name="th0r3nt",
        tier="high",
        category="subject",
        description="Создатель",
        status="Online",
    )
    assert res_create.is_success is True
    ms_id = res_create.message.split("ID: ")[1].strip()

    # Читаем
    res_get = await mental_states_manager.get_mental_states()
    assert "th0r3nt" in res_get.message

    # Обновляем
    res_update = await mental_states_manager.update_mental_state(
        ms_id, status="Отошел за кофе"
    )
    assert res_update.is_success is True

    res_get_updated = await mental_states_manager.get_mental_states()
    assert "Отошел за кофе" in res_get_updated.message

    # Удаляем
    res_del = await mental_states_manager.delete_mental_state(ms_id)
    assert res_del.is_success is True

    res_get_empty = await mental_states_manager.get_mental_states()
    assert "Список MentalState пуст" in res_get_empty.message


# ===================================================================
# TESTS: DRIVES
# ===================================================================


@pytest.mark.asyncio
async def test_drives_bootstrap_and_context(drives_manager):
    """Тест: Базовые драйвы успешно создаются при первом запуске, дефицит считается корректно."""

    # 1. Бутстрап (должно создаться 3 базовых мотивации: Curiosity, Social, Mastery)
    await drives_manager.bootstrap_fundamental_drives()

    # 2. Проверяем контекст
    context = await drives_manager.get_context_block()
    assert "Curiosity" in context
    assert "Social" in context
    assert "Mastery" in context
    # При создании last_satisfied_at = сейчас, значит дефицит должен быть 0/100
    assert "Дефицит: 0/100" in context


@pytest.mark.asyncio
async def test_drives_satisfy_drive(drives_manager):
    """Тест: удовлетворение драйва обновляет рефлексию и историю."""

    await drives_manager.bootstrap_fundamental_drives()

    # Агент удовлетворил любопытство
    res = await drives_manager.satisfy_drive(
        drive_name="curiosity", reflection_summary="Прочитала статью на Хабре про вектора."
    )
    assert res.is_success is True

    context = await drives_manager.get_context_block()
    assert "Прочитала статью на Хабре про вектора." in context


@pytest.mark.asyncio
async def test_drives_custom_crud_and_limits(drives_manager):
    """Тест: Создание кастомного драйва, лимиты и удаление."""

    # Создаем кастомные (используем точный регистр для надежности SQLite)
    res_1 = await drives_manager.create_custom_drive("Мониторинг логов", "Чек ошибок")
    res_2 = await drives_manager.create_custom_drive("Проверка почты", "Чек писем")

    assert res_1.is_success is True
    assert res_2.is_success is True

    # Пытаемся превысить лимит (max_custom = 2)
    res_fail = await drives_manager.create_custom_drive("Лишний", "Не влезет")
    assert res_fail.is_success is False
    assert "Достигнут лимит" in res_fail.message

    # Удаляем кастомный (передаем в том же регистре)
    res_del = await drives_manager.delete_custom_drive("Мониторинг логов")
    assert res_del.is_success is True


@pytest.mark.asyncio
async def test_drives_cannot_delete_fundamental(drives_manager):
    """Тест: Система защищает базовые драйвы от удаления агентом."""

    await drives_manager.bootstrap_fundamental_drives()

    # Пытаемся удалить вшитый драйв (с большой буквы, как он создается в БД)
    res_del = await drives_manager.delete_custom_drive("Social")
    assert res_del.is_success is False
    assert "Базовые (Fundamental) драйвы нельзя удалить" in res_del.message

import pytest


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

import pytest


@pytest.mark.asyncio
async def test_create_and_get_tasks(tasks_manager):
    res_create = await tasks_manager.create_task(
        title="Написать тесты", description="Сегодня", quadrant=2, tags=["type:routine"]
    )
    assert res_create.is_success is True
    assert "ID:" in res_create.message

    task_id = res_create.message.split("ID: ")[1].strip()

    context = await tasks_manager.get_context_block()
    assert "Написать тесты" in context
    assert task_id in context
    assert "Quadrant 2" in context


@pytest.mark.asyncio
async def test_update_task(tasks_manager):
    res_create = await tasks_manager.create_task(
        title="Старая задача", description="Оп", quadrant=2, tags=["type:routine"]
    )
    task_id = res_create.message.split("ID: ")[1].strip()

    res_update = await tasks_manager.update_task(task_id, title="Новая задача")
    assert res_update.is_success is True

    context = await tasks_manager.get_context_block()
    assert "Новая задача" in context
    assert "Старая задача" not in context


@pytest.mark.asyncio
async def test_delete_task(tasks_manager):
    res_create = await tasks_manager.create_task(
        title="Задача на удаление", description="Оп", quadrant=2, tags=["type:routine"]
    )
    task_id = res_create.message.split("ID: ")[1].strip()

    res_delete = await tasks_manager.delete_task(task_id)
    assert res_delete.is_success is True

    context = await tasks_manager.get_context_block()
    assert "The task list is empty" in context


@pytest.mark.asyncio
async def test_add_task_limit(tasks_manager):
    await tasks_manager.create_task(
        title="Task 1", description="1", quadrant=2, tags=["type:routine"]
    )
    await tasks_manager.create_task(
        title="Task 2", description="2", quadrant=2, tags=["type:routine"]
    )

    res_fail = await tasks_manager.create_task(
        title="Task 3", description="3", quadrant=2, tags=["type:routine"]
    )
    assert res_fail.is_success is False
    assert "limit reached" in res_fail.message


def test_validate_tags_hallucinations(tasks_manager):
    is_valid, err, tags = tasks_manager._validate_tags("['type:routine', 'priority:high']")
    assert is_valid is True
    assert tags == ["type:routine", "priority:high"]

    is_valid, err, tags = tasks_manager._validate_tags("domain:code")
    assert is_valid is True
    assert tags == ["domain:code"]

    is_valid, err, tags = tasks_manager._validate_tags(["domain:magic"])
    assert is_valid is False
    assert len(tags) == 0

    is_valid, err, tags = tasks_manager._validate_tags(None)
    assert is_valid is True
    assert tags == []


@pytest.mark.asyncio
async def test_move_task_to_quadrant(tasks_manager):
    res_create = await tasks_manager.create_task(title="Задача", description="Оп", quadrant=2)
    task_id = res_create.message.split("ID: ")[1].strip()

    res_move = await tasks_manager.move_task_to_quadrant(task_id, 1)
    assert res_move.is_success is True

    context = await tasks_manager.get_context_block()
    assert "Quadrant 1" in context
    assert task_id in context

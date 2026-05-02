import pytest


@pytest.mark.asyncio
async def test_create_and_get_tasks(tasks_manager):
    res_create = await tasks_manager.create_task("Написать тесты", "Сегодня", ["type:routine"])
    assert res_create.is_success is True
    assert "ID:" in res_create.message

    task_id = res_create.message.split("ID: ")[1].strip()

    context = await tasks_manager.get_context_block()
    assert "Написать тесты" in context
    assert task_id in context


@pytest.mark.asyncio
async def test_update_task(tasks_manager):
    res_create = await tasks_manager.create_task("Старая задача", "Оп", ["type:routine"])
    task_id = res_create.message.split("ID: ")[1].strip()

    res_update = await tasks_manager.update_task(task_id, title="Новая задача")
    assert res_update.is_success is True

    context = await tasks_manager.get_context_block()
    assert "Новая задача" in context
    assert "Старая задача" not in context


@pytest.mark.asyncio
async def test_delete_task(tasks_manager):
    res_create = await tasks_manager.create_task("Задача на удаление", "Оп", ["type:routine"])
    task_id = res_create.message.split("ID: ")[1].strip()

    res_delete = await tasks_manager.delete_task(task_id)
    assert res_delete.is_success is True

    context = await tasks_manager.get_context_block()
    assert "Список задач пуст" in context


@pytest.mark.asyncio
async def test_add_task_limit(tasks_manager):
    await tasks_manager.create_task("Task 1", "1", ["type:routine"])
    await tasks_manager.create_task("Task 2", "2", ["type:routine"])

    res_fail = await tasks_manager.create_task("Task 3", "3", ["type:routine"])
    assert res_fail.is_success is False
    assert "Достигнут лимит" in res_fail.message


def test_validate_tags_hallucinations(tasks_manager):
    """Тест: защита БД от некорректного формата тегов, сгенерированных LLM."""

    # 1. LLM присылает строку вместо списка (классическая галлюцинация)
    is_valid, err, tags = tasks_manager._validate_tags("['type:routine', 'priority:high']")
    assert is_valid is True
    assert tags == ["type:routine", "priority:high"]

    # 2. LLM присылает одиночный тег как строку
    is_valid, err, tags = tasks_manager._validate_tags("domain:code")
    assert is_valid is True
    assert tags == ["domain:code"]

    # 3. LLM выдумывает несуществующий тег
    is_valid, err, tags = tasks_manager._validate_tags(["domain:magic"])
    assert is_valid is False
    assert "недопустим" in err
    assert len(tags) == 0

    # 4. Передача None (допустимо, вернется пустой список)
    is_valid, err, tags = tasks_manager._validate_tags(None)
    assert is_valid is True
    assert tags == []

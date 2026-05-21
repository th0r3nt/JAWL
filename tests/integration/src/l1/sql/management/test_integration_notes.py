import pytest


@pytest.mark.asyncio
async def test_notes_crud_lifecycle(notes_manager):
    """Тест: Полный жизненный цикл заметки."""
    # 1. Создание
    res_add = await notes_manager.add_note("Купить сервер")
    assert res_add.is_success is True
    note_id = res_add.message.split("ID: ")[1].strip(").")

    # Проверка контекста (появилась ли она в промпте)
    context = await notes_manager.get_context_block()
    assert "Купить сервер" in context
    assert note_id in context

    # 2. Обновление
    res_upd = await notes_manager.update_note(note_id, "Купить два сервера")
    assert res_upd.is_success is True

    # Читаем полностью
    res_list = await notes_manager.list_all_notes()
    assert "Купить два сервера" in res_list.message

    # 3. Удаление
    res_del = await notes_manager.delete_note(note_id)
    assert res_del.is_success is True

    # Контекст должен стать пустым
    context_empty = await notes_manager.get_context_block()
    assert context_empty == ""


@pytest.mark.asyncio
async def test_notes_limit_enforcement(notes_manager):
    """Тест: Лимит заметок строго соблюдается."""
    await notes_manager.add_note("Note 1")
    await notes_manager.add_note("Note 2")

    # Третья должна упасть, т.к. max_notes=2
    res_fail = await notes_manager.add_note("Note 3")
    assert res_fail.is_success is False
    assert "limit reached" in res_fail.message

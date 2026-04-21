import pytest


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

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
    assert "The list of entities is empty" in res_get_empty.message


@pytest.mark.asyncio
async def test_update_mental_state_allows_clearing_description_and_status(
    mental_states_manager,
):
    """Раньше update использовал `if description:` вместо `is not None`, и emptyя
    строка молча игнорировалась. Агент не мог очистить поле, получая в ответ
    'обновлен'. Это silent update failure.
    """
    res_create = await mental_states_manager.create_mental_state(
        name="some_server",
        tier="medium",
        category="object",
        description="Сервер с старым описанием",
        status="down",
    )
    assert res_create.is_success is True
    ms_id = res_create.message.split("ID: ")[1].strip()

    # Пробуем очистить поля emptyой строкой
    res_update = await mental_states_manager.update_mental_state(
        ms_id, description="", status=""
    )
    assert res_update.is_success is True

    res_get = await mental_states_manager.get_mental_states()
    # Старое описание/статус не должны висеть в контексте
    assert "Старым описанием" not in res_get.message
    assert " down" not in res_get.message

    await mental_states_manager.delete_mental_state(ms_id)


@pytest.mark.asyncio
async def test_mental_states_radar_relations_and_attitude(mental_states_manager):
    res_create = await mental_states_manager.create_mental_state(
        name="ServerX",
        tier="high",
        category="object",
        description="A bad server",
        status="Offline",
        attitude="Hostile",
        directives="Never deploy on Friday",
        epistemic_state="Senior in breaking down",
        relations={"id_admin": "Hates the admin"},
    )
    assert res_create.is_success is True

    res_get = await mental_states_manager.get_mental_states()
    context = res_get.message
    assert "Attitude: Hostile" in context
    assert "Never deploy on Friday" in context
    assert "Senior in breaking down" in context
    assert "Hates the admin" in context

import pytest
from src.l2_interfaces.meta.skills.level_safe import MetaSafe
from src.utils.event.registry import Events


@pytest.mark.asyncio
async def test_meta_safe_change_model(meta_client):
    skills = MetaSafe(meta_client)

    # Успешная смена
    res = await skills.change_model("gpt-4o")
    assert res.is_success is True
    assert meta_client.agent_state.llm_model == "gpt-4o"

    # Нельзя поставить модель, которой нет в списке
    res_fail = await skills.change_model("llama-3")
    assert res_fail.is_success is False
    assert "unavailable" in res_fail.message


@pytest.mark.asyncio
async def test_meta_safe_add_remove_models(meta_client):
    skills = MetaSafe(meta_client)

    # Добавляем
    res_add = await skills.add_available_model("llama-3")
    assert res_add.is_success is True
    assert "llama-3" in meta_client.available_models

    # Удаляем
    res_del = await skills.remove_available_model("gpt-4o")
    assert res_del.is_success is True
    assert "gpt-4o" not in meta_client.available_models

    # Нельзя удалить текущую рабочую модель
    res_fail = await skills.remove_available_model(meta_client.agent_state.llm_model)
    assert res_fail.is_success is False
    assert "currently active model" in res_fail.message


@pytest.mark.asyncio
async def test_meta_safe_change_temperature(meta_client):
    skills = MetaSafe(meta_client)

    res = await skills.change_temperature(0.9)
    assert res.is_success is True
    assert meta_client.agent_state.temperature == 0.9

    res_fail = await skills.change_temperature(5.0)
    assert res_fail.is_success is False


@pytest.mark.asyncio
async def test_meta_safe_set_current_goal(meta_client):
    """Тест: Навык установки текущей цели корректно обновляет L0 State агента."""
    skills = MetaSafe(meta_client)

    # Установка цели
    res = await skills.set_current_goal("Протестировать модуль X")
    assert res.is_success is True
    assert meta_client.agent_state.current_goal == "Протестировать модуль X"
    # assert "установлена" in res.message

    # Сброс цели
    res_clear = await skills.set_current_goal("   ")
    assert res_clear.is_success is True
    assert meta_client.agent_state.current_goal == ""
    # assert "сброшена" in res_clear.message


@pytest.mark.asyncio
async def test_meta_safe_sleep_skill(meta_client):
    """Тест: Навык sleep корректно публикует событие в EventBus и запрашивает завершение цикла."""
    skills = MetaSafe(meta_client)

    # 1. Валидный вызов
    res = await skills.sleep(duration=3600, depth="deep")
    assert res.is_success is True
    assert res.terminate_loop is True
    assert "3600 seconds" in res.message
    meta_client.bus.publish.assert_called_with(
        Events.SYSTEM_SLEEP_REQUESTED, duration=3600, depth="deep"
    )

    # 2. Невалидная глубина
    res_bad_depth = await skills.sleep(duration=60, depth="invalid")
    assert res_bad_depth.is_success is False
    assert res_bad_depth.terminate_loop is False

    # 3. Невалидная длительность
    res_bad_dur = await skills.sleep(duration=-5)
    assert res_bad_dur.is_success is False
    assert res_bad_dur.terminate_loop is False
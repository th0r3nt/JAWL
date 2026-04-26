import pytest
from src.l2_interfaces.meta.skills.level_safe import MetaSafe


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
    assert "недоступна" in res_fail.message


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
    assert "используется в данный момент" in res_fail.message


@pytest.mark.asyncio
async def test_meta_safe_change_temperature(meta_client):
    skills = MetaSafe(meta_client)

    res = await skills.change_temperature(0.9)
    assert res.is_success is True
    assert meta_client.agent_state.temperature == 0.9

    res_fail = await skills.change_temperature(5.0)
    assert res_fail.is_success is False

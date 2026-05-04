import pytest
from src.l2_interfaces.code_graph.state import CodeGraphState


def test_code_graph_state_save_and_load(tmp_path):
    """Тест: Стейт сохраняет проиндексированные проекты на диск и восстанавливает их."""
    state = CodeGraphState(data_dir=tmp_path)

    state.active_indexes["test_project"] = "sandbox/test"
    state.save()

    # Создаем новый стейт, он должен загрузить данные с диска
    new_state = CodeGraphState(data_dir=tmp_path)
    assert "test_project" in new_state.active_indexes
    assert new_state.active_indexes["test_project"] == "sandbox/test"


@pytest.mark.asyncio
async def test_code_graph_client_context(cg_client):
    """Тест: Блок контекста отдает правильную информацию агенту."""
    # Оффлайн
    cg_client.state.is_online = False
    assert "[OFF]" in await cg_client.get_context_block()

    # Онлайн, но пусто
    cg_client.state.is_online = True
    assert "Активных графов нет" in await cg_client.get_context_block()

    # Онлайн с проектами
    cg_client.state.active_indexes["my_api"] = "sandbox/api"
    ctx = await cg_client.get_context_block()
    assert "[ON]" in ctx
    assert "`my_api`" in ctx
    assert "sandbox/api" in ctx

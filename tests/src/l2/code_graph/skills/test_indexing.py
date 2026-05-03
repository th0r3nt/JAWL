import pytest
from unittest.mock import patch, MagicMock

from src.l2_interfaces.code_graph.skills.indexing import CodeGraphIndexing


@pytest.fixture
def indexing_skill(cg_client, mock_graph_crud, mock_vector_crud):
    return CodeGraphIndexing(cg_client, mock_graph_crud, mock_vector_crud)


@pytest.mark.asyncio
@patch("src.l2_interfaces.code_graph.skills.indexing.asyncio.to_thread")
async def test_index_codebase_success(mock_to_thread, indexing_skill):
    """Тест: Успешная индексация сохраняет данные в стейт."""
    mock_to_thread.return_value = {"files": 10, "classes": 5, "functions": 20}
    
    # Сбрасываем side_effect фикстуры и подсовываем полностью контролируемый мок
    mock_path = MagicMock()
    mock_path.is_dir.return_value = True
    mock_path.name = "my_app"
    mock_path.relative_to.return_value.as_posix.return_value = "sandbox/my_app"
    
    indexing_skill.client.host_os.validate_path.side_effect = None
    indexing_skill.client.host_os.validate_path.return_value = mock_path

    res = await indexing_skill.index_codebase("sandbox/my_app", "my_app")

    assert res.is_success is True
    assert "10 файлов" in res.message
    assert "my_app" in indexing_skill.client.state.active_indexes
    indexing_skill.client.host_os.validate_path.assert_called_once()


@pytest.mark.asyncio
async def test_delete_index_success(indexing_skill):
    """Тест: Удаление индекса стирает данные из БД и стейта."""
    indexing_skill.client.state.active_indexes["old_app"] = "sandbox/old"

    res = await indexing_skill.delete_index("old_app")

    assert res.is_success is True
    assert "old_app" not in indexing_skill.client.state.active_indexes
    indexing_skill.graph.delete_project.assert_awaited_once_with("old_app")
    indexing_skill.vector.delete_project.assert_awaited_once_with("old_app")

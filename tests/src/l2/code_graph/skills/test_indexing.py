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


@pytest.mark.asyncio
async def test_indexing_process_imports_resolution(tmp_path, indexing_skill):
    """Регрессионный тест: AST парсер корректно резолвит абсолютные и относительные импорты."""

    # Создаем фейковую структуру файлов (чтобы парсер мог построить module_map)
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()

    pkg_dir = project_dir / "pkg"
    pkg_dir.mkdir()

    # Файлы
    (project_dir / "main.py").write_text(
        "from pkg.utils import helper\nimport sys", encoding="utf-8"
    )
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "utils.py").write_text("def helper(): pass", encoding="utf-8")
    (pkg_dir / "core.py").write_text("from .utils import helper", encoding="utf-8")

    # Запускаем синхронный парсер
    indexing_skill.client.config.exclude_dirs = []

    import asyncio

    await asyncio.to_thread(indexing_skill._parse_and_build_sync, project_dir, "test_proj")

    # Извлекаем все вызовы создания связей IMPORTS
    calls = indexing_skill.graph.link_nodes.call_args_list
    import_calls = [c for c in calls if c[0][2] == "IMPORTS"]

    # Проверка 1: Абсолютный импорт (main.py -> pkg/utils.py)
    assert any(
        c[0][0] == "test_proj::main.py" and c[0][1] == "test_proj::pkg/utils.py"
        for c in import_calls
    ), "Абсолютный импорт не срезолвлен."

    # Проверка 2: Относительный импорт (pkg/core.py -> pkg/utils.py)
    assert any(
        c[0][0] == "test_proj::pkg/core.py" and c[0][1] == "test_proj::pkg/utils.py"
        for c in import_calls
    ), "Относительный импорт (с точкой) не срезолвлен."

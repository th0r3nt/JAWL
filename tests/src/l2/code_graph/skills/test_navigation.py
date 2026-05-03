import pytest
from src.l2_interfaces.code_graph.skills.navigation import CodeGraphNavigation


@pytest.fixture
def nav_skill(cg_client, mock_graph_crud, mock_vector_crud):
    cg_client.state.active_indexes["test_prj"] = "sandbox/test"
    return CodeGraphNavigation(cg_client, mock_graph_crud, mock_vector_crud)


@pytest.mark.asyncio
async def test_search_code_semantic(nav_skill):
    """Тест: Семантический поиск корректно форматирует ответы Векторной БД."""
    nav_skill.vector.search.return_value = [
        {
            "node_id": "test_prj::src/api.py::Auth",
            "type": "CLASS",
            "score": 0.95,
            "text": "Handles authentication.",
        }
    ]

    res = await nav_skill.search_code_semantic("test_prj", "auth logic")

    assert res.is_success is True
    assert "`src/api.py::Auth`" in res.message
    assert "Handles authentication." in res.message


@pytest.mark.asyncio
async def test_trace_dependencies(nav_skill):
    """Тест: Поиск связей (Blast Radius) корректно объединяет входящие и исходящие связи."""
    nav_skill.graph.get_usages.return_value = [
        {"relation": "IMPORTS", "id": "test_prj::src/main.py", "type": "FILE"}
    ]
    nav_skill.graph.get_dependencies.return_value = [
        {"relation": "CONTAINS", "id": "test_prj::src/api.py::Auth", "type": "CLASS"}
    ]

    res = await nav_skill.trace_dependencies("test_prj", "src/api.py")

    assert res.is_success is True
    assert "<- src/main.py (FILE)" in res.message
    assert "-> src/api.py::Auth (CLASS)" in res.message


@pytest.mark.asyncio
async def test_get_file_structure(nav_skill):
    """Тест: Получение структуры файла (оглавления)."""

    # Имитируем, что файл содержит класс Auth, а класс Auth содержит метод login
    async def mock_get_deps(node_id):
        if node_id == "test_prj::src/api.py":
            return [
                {"relation": "CONTAINS", "type": "CLASS", "id": "test_prj::src/api.py::Auth"}
            ]
        elif node_id == "test_prj::src/api.py::Auth":
            return [
                {
                    "relation": "DEFINES",
                    "type": "FUNCTION",
                    "id": "test_prj::src/api.py::Auth.login",
                }
            ]
        return []

    nav_skill.graph.get_dependencies.side_effect = mock_get_deps

    res = await nav_skill.get_file_structure("test_prj", "src/api.py")

    assert res.is_success is True
    assert "[CLASS] Auth" in res.message
    assert "[METHOD] login" in res.message

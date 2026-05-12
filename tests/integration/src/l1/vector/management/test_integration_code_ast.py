"""
Интеграционные тесты для векторной коллекции Code Graph (code_ast).
Проверяют сохранение докстрингов, семантический поиск с фильтрацией по проектам и каскадное удаление.
"""

import pytest
import pytest_asyncio
from qdrant_client import models

from src.l1_databases.vector.collections import VectorCollection
from src.l1_databases.vector.management.code_ast import VectorCodeAST


@pytest_asyncio.fixture
async def ast_manager(vector_db, mock_embedding):
    """Инициализирует менеджер AST и гарантирует наличие коллекции code_ast."""

    # Динамически создаем коллекцию для этого теста, если её нет
    if not await vector_db.client.collection_exists("code_ast"):
        await vector_db.client.create_collection(
            collection_name="code_ast",
            vectors_config=models.VectorParams(
                size=3, distance=models.Distance.COSINE  # Размер вектора из mock_embedding
            ),
        )

    col = VectorCollection(vector_db, "code_ast")

    return VectorCodeAST(
        db=vector_db, embedding_model=mock_embedding, collection=col, similarity_threshold=0.1
    )


@pytest.mark.asyncio
async def test_code_ast_save_and_cross_project_search(ast_manager):
    """
    Тест: Проверка сохранения и фильтрации.
    Поиск должен строго изолировать результаты по project_id,
    чтобы агент не нашел код из другого проекта с похожим смыслом.
    """
    # Сохраняем "яблоко" в проект А
    await ast_manager.save_doc("node1", "Это класс яблоко", "project_A", "CLASS")

    # Сохраняем "машину" и еще одно "яблоко" в проект Б
    await ast_manager.save_doc("node2", "Это двигатель машины", "project_B", "CLASS")
    await ast_manager.save_doc("node3", "Еще одно яблоко", "project_B", "FUNCTION")

    # Ищем по смыслу "яблоко" (вектор 1.0, 0.0, 0.0) СТРОГО в project_B
    res = await ast_manager.search("яблоко", project_id="project_B", limit=5)

    assert len(res) == 1
    assert res[0]["node_id"] == "node3"
    assert res[0]["type"] == "FUNCTION"
    assert "Еще одно яблоко" in res[0]["text"]


@pytest.mark.asyncio
async def test_code_ast_delete_project(ast_manager):
    """
    Тест: Удаление проекта физически вычищает только его вектора из базы.
    """
    await ast_manager.save_doc("n1", "Яблоко 1", "proj_1", "FILE")
    await ast_manager.save_doc("n2", "Яблоко 2", "proj_2", "FILE")

    # Удаляем proj_1
    await ast_manager.delete_project("proj_1")

    # Поиск в proj_1 должен быть пустым
    res1 = await ast_manager.search("Яблоко", project_id="proj_1")
    assert len(res1) == 0

    # В proj_2 вектор должен остаться в целости
    res2 = await ast_manager.search("Яблоко", project_id="proj_2")
    assert len(res2) == 1
    assert res2[0]["node_id"] == "n2"

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l3_agent.context.rag.search.vector import VectorSearchWrapper
from src.l3_agent.context.rag.search.graph import GraphSearchWrapper


@pytest.mark.asyncio
async def test_vector_search_wrapper_deduplication():
    """
    Тест: VectorSearchWrapper корректно дедуплицирует записи.
    Если поиск по knowledge и thoughts вернул одну и ту же запись (по ID),
    остаться должна та, у которой score (релевантность) выше.
    """
    mock_knowledge = MagicMock()
    mock_knowledge.collection.name = "knowledge"
    mock_knowledge.similarity_threshold = 0.5

    mock_thoughts = MagicMock()
    mock_thoughts.collection.name = "thoughts"
    mock_thoughts.similarity_threshold = 0.5

    wrapper = VectorSearchWrapper(mock_knowledge, mock_thoughts, top_k=2)

    # Имитируем ответы от Qdrant Client
    pt1_low = MagicMock(id="point_A", score=0.6, payload={"text": "Fact A", "tags": []})
    pt1_high = MagicMock(id="point_A", score=0.9, payload={"text": "Fact A", "tags": []})
    pt2 = MagicMock(id="point_B", score=0.7, payload={"text": "Fact B", "tags": []})

    # База знаний вернула point_A с низким скором
    mock_knowledge.db.client.search = AsyncMock(return_value=[pt1_low, pt2])
    # База мыслей вернула point_A с высоким скором (например, мысль более релевантна)
    mock_thoughts.db.client.search = AsyncMock(return_value=[pt1_high])

    # Запускаем батчевый поиск по одному вектору
    results = await wrapper.search_batch([[0.1, 0.2, 0.3]])

    # Ожидаем 2 уникальных результата (point_A и point_B)
    assert len(results) == 2

    # Ищем point_A в результатах и проверяем его score
    res_a = next(r for r in results if r["id"] == "point_A")
    assert res_a["score"] == 0.9  # Должен сохраниться наибольший score
    assert res_a["collection"] == "thoughts"  # Коллекция, откуда пришел high_score


@pytest.mark.asyncio
async def test_graph_search_wrapper_neighborhood():
    """
    Тест: GraphSearchWrapper корректно извлекает узел и парсит его связи (edges).
    """
    mock_graph_manager = MagicMock()
    mock_graph_manager.db.conn = MagicMock()

    # Имитируем лок
    class DummyLock:
        async def __aenter__(self):
            pass

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_graph_manager.db.write_lock = DummyLock()
    wrapper = GraphSearchWrapper(mock_graph_manager)

    # 1. Мок для самого узла (возвращается 1 раз)
    mock_node_res = MagicMock()
    mock_node_res.has_next.side_effect = [True, False]
    mock_node_res.get_next.return_value = ["Основатель Apple", "PERSON", True]

    # 2. Мок для найденной связи (возвращается 1 раз)
    mock_edge_out = MagicMock()
    mock_edge_out.has_next.side_effect = [True, False]
    mock_edge_out.get_next.return_value = ["Apple"]

    # 3. Мок-пустышка для остальных связей (будет вызываться много раз, поэтому return_value)
    mock_edge_empty = MagicMock()
    mock_edge_empty.has_next.return_value = False

    out_called = False

    def fake_execute(query):
        nonlocal out_called
        if "description, n.category" in query:
            return mock_node_res
        elif "->(b" in query:
            if "LIMIT" in query and not out_called:
                out_called = True
                return mock_edge_out
            return mock_edge_empty
        elif "<-[e" in query:
            return mock_edge_empty
        return mock_edge_empty

    mock_graph_manager.db.conn.execute.side_effect = fake_execute

    results = await wrapper.get_nodes_with_neighborhood(["Стив Джобс"])

    assert len(results) == 1
    node = results[0]
    assert node["name"] == "Стив Джобс"
    assert node["description"] == "Основатель Apple"
    assert node["category"] == "PERSON"
    assert any("-> (Apple)" in rel for rel in node["relations"])

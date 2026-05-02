import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.utils.settings import RAGConfig
from src.l0_state.agent.state import AgentState
from src.l1_databases.vector.db import VectorDB
from src.l1_databases.vector.collections import VectorCollection
from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts
from src.l1_databases.graph.manager import GraphManager
from src.l3_agent.context.rag.memories import RAGMemories

from tests.src.l1.vector.conftest import MockEmbeddingModel


@pytest.mark.asyncio
async def test_integration_auto_graphrag_context_injection(tmp_path: Path):
    """
    Интеграционный хардкорный тест: "Входящее сообщение -> Вектор + Граф -> Семантический резолвинг -> Промпт".
    Проверяет гибридную логику Vector-Graph RAG с использованием RapidFuzz для русского языка.
    """

    vector_db_path = tmp_path / "qdrant_test"
    vector_db = VectorDB(
        db_path=str(vector_db_path), collections=["knowledge", "thoughts"], vector_size=3
    )
    await vector_db.connect()

    mock_emb = MockEmbeddingModel()

    col_know = VectorCollection(vector_db, "knowledge")
    knowledge = VectorKnowledge(vector_db, mock_emb, col_know, similarity_threshold=0.5)
    col_thou = VectorCollection(vector_db, "thoughts")
    thoughts = VectorThoughts(vector_db, mock_emb, col_thou, similarity_threshold=0.5)

    graph_db_path = tmp_path / "kuzu_test"
    graph_manager = GraphManager(db_path=graph_db_path, max_nodes=50)
    await graph_manager.connect()

    # Вектор
    await knowledge.save_knowledge(
        "Секретный код от хранилища Яблоко: 4242", tags=["type:fact"]
    )

    # Граф
    await graph_manager.crud.add_concept("Стив Джобс", "Основатель.", "PERSON")
    await graph_manager.crud.add_concept(
        "Apple", "Корпорация, делающая технику.", "ORGANIZATION"
    )
    await graph_manager.crud.link_concepts("Стив Джобс", "Apple", "OWNS", "Создал компанию")

    telethon_state = MagicMock()
    telethon_state.last_chats = ""
    agent_state = AgentState(current_step=1)

    # Включаем RapidFuzz для нечеткого поиска, чтобы доказать,
    # что он справится с падежами в русском языке ("Стива Джобса" -> "Стив Джобс")
    rag_config = RAGConfig(
        enabled=True,
        extraction_engine="rapidfuzz",
        depth_limit=2,
        max_vector_blocks=5,
        max_graph_nodes=5,
        max_query_chars=200,
    )

    rag = RAGMemories(
        vector_knowledge=knowledge,
        vector_thoughts=thoughts,
        graph_manager=graph_manager,
        embedding_model=mock_emb,
        telethon_state=telethon_state,
        agent_state=agent_state,
        rag_config=rag_config,
    )

    # Пишем сообщение с падежами ("Стива Джобса")
    payload = {
        "sender_name": "Boss",
        "message": "Агент, расскажи про Стива Джобса и какое-то Яблоко?",
        "raw_text": "Агент, расскажи про Стива Джобса и какое-то Яблоко?",
    }

    context_block = await rag.get_context_block(payload=payload, missed_events=[])

    assert "RELEVANT INFORMATION" in context_block

    assert "Секретный код от хранилища Яблоко: 4242" in context_block
    assert "type:fact" in context_block

    # Граф должен успешно срезолвить узел, несмотря на падежи
    assert "Узел: Стив Джобс" in context_block
    assert "Основатель." in context_block

    assert "-[OWNS]-> (Apple)" in context_block

    await vector_db.disconnect()
    await graph_manager.disconnect()
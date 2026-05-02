"""
Оркестратор гибридного поиска (Vector-Graph RAG).

Управляет итеративным циклом (Depth N):
1. Извлекает запросы и узлы.
2. Параллельно ищет в Vector DB и Graph DB.
3. Осуществляет асимметричную семантическую маршрутизацию (Vector-Graph RAG):
   ищет узлы в найденных векторных текстах, а описания узлов использует как
   новые текстовые запросы для векторов.
"""

from typing import List, Dict, Any, Set

from src.utils.logger import system_logger
from src.utils.settings import RAGConfig

from src.l1_databases.vector.embedding import EmbeddingModel
from src.l3_agent.context.rag.entity_extractor import EntityExtractor
from src.l3_agent.context.rag.search.vector import VectorSearchWrapper
from src.l3_agent.context.rag.search.graph import GraphSearchWrapper


class GraphRAGOrchestrator:
    """Ядро алгоритма гибридного RAG."""

    def __init__(
        self,
        vector_search: VectorSearchWrapper,
        graph_search: GraphSearchWrapper,
        extractor: EntityExtractor,
        embedding_model: EmbeddingModel,
        config: RAGConfig,
    ) -> None:
        self.vector_search = vector_search
        self.graph_search = graph_search
        self.extractor = extractor
        self.embedding_model = embedding_model
        self.config = config

    async def run(self, input_texts: List[str]) -> str:
        """
        Запускает цикл Vector-Graph RAG для массива входящих триггеров (текстов).

        Args:
            input_texts: Массив первичных текстов (мысли агента, сообщения пользователя).

        Returns:
            Сформированный Markdown-блок с контекстом для LLM.
        """

        if not input_texts:
            return ""

        # Синхронизируем словарь графа для Aho-Corasick
        vocab = await self.graph_search.get_all_node_names()
        self.extractor.build_graph_vocabulary(vocab)

        # Инициализируем хранилища состояний (защита от зацикливания)
        visited_vector_queries: Set[str] = set()
        visited_graph_nodes: Set[str] = set()

        all_vector_results: Dict[str, Dict[str, Any]] = {}
        all_graph_results: Dict[str, Dict[str, Any]] = {}

        # Первичное извлечение якорей (Depth 0)
        current_vector_queries: Set[str] = set()
        current_graph_nodes: Set[str] = set()

        for text in input_texts:
            current_vector_queries.update(self.extractor.extract_vector_queries(text))
            current_graph_nodes.update(self.extractor.extract_graph_nodes(text))

        system_logger.info(
            f"[GraphRAG] Старт цикла. Извлечено: {len(current_vector_queries)} векторных якорей, {len(current_graph_nodes)} графовых узлов."
        )

        # Главный цикл семантического резолвинга
        for depth in range(self.config.depth_limit):
            # Отсекаем то, что уже искали ранее
            current_vector_queries -= visited_vector_queries
            current_graph_nodes -= visited_graph_nodes

            if not current_vector_queries and not current_graph_nodes:
                system_logger.debug(
                    f"[GraphRAG] Early Exit на глубине {depth} (нет новых якорей)."
                )
                break

            visited_vector_queries.update(current_vector_queries)
            visited_graph_nodes.update(current_graph_nodes)

            # ==========================================
            # I/O: Запросы к базам данных
            # ==========================================

            vector_results = []
            if current_vector_queries:
                # Батчевая генерация эмбеддингов (быстро)
                embeddings = await self.embedding_model.get_embeddings_batch(
                    list(current_vector_queries)
                )
                vector_results = await self.vector_search.search_batch(embeddings)

            graph_results = []
            if current_graph_nodes:
                graph_results = await self.graph_search.get_nodes_with_neighborhood(
                    list(current_graph_nodes)
                )

            # ====================================================
            # Синхронизация контекстов (Vector-Graph)
            # ====================================================

            new_vector_queries: Set[str] = set()
            new_graph_nodes: Set[str] = set()

            # Обработка векторов
            for v_res in vector_results:
                v_id = v_res["id"]
                # Если нашли новый результат или с бОльшим score - сохраняем
                if (
                    v_id not in all_vector_results
                    or v_res["score"] > all_vector_results[v_id]["score"]
                ):
                    all_vector_results[v_id] = v_res

                # Ищем упоминания узлов графа в найденном векторном тексте
                extracted_nodes = self.extractor.extract_graph_nodes(v_res["text"])
                new_graph_nodes.update(extracted_nodes)

            # Обработка графов
            for g_res in graph_results:
                g_name = g_res["name"]
                if g_name not in all_graph_results:
                    all_graph_results[g_name] = g_res

                # Используем описание узла как новый текстовый запрос для Векторной БД
                desc = g_res["description"]
                if desc:
                    extracted_queries = self.extractor.extract_vector_queries(desc)
                    new_vector_queries.update(extracted_queries)

            # Передаем эстафету следующему шагу
            current_vector_queries = new_vector_queries
            current_graph_nodes = new_graph_nodes

        # Сборка и форматирование финала
        return self._format_markdown(all_vector_results, all_graph_results)

    def _format_markdown(
        self,
        vector_results: Dict[str, Dict[str, Any]],
        graph_results: Dict[str, Dict[str, Any]],
    ) -> str:
        """Сортирует, обрезает по лимитам и собирает Markdown-текст для промпта."""

        # Сортируем вектора по убыванию релевантности
        sorted_vectors = sorted(
            vector_results.values(), key=lambda x: x["score"], reverse=True
        )
        top_vectors = sorted_vectors[: self.config.max_vector_blocks]

        # Узлы графа пока берем как есть (первые найденные), обрезаем по лимиту
        top_graph = list(graph_results.values())[: self.config.max_graph_nodes]

        if not top_vectors and not top_graph:
            return ""

        blocks = []

        if top_graph:
            blocks.append("### Карта связей:")
            for node in top_graph:
                rels = (
                    "\n    ".join(node["relations"])
                    if node["relations"]
                    else "    (нет связей)"
                )
                blocks.append(
                    f"- Узел: {node['name']} (Тип: {node['category']})\n"
                    f"  Описание: {node['description']}\n"
                    f"  Связи:\n    {rels}"
                )

        if top_vectors:
            blocks.append("\n### Воспоминания:")
            for vec in top_vectors:
                tags_str = f"[{', '.join(vec['tags'])}]" if vec["tags"] else "[Без тегов]"
                blocks.append(
                    f"[ID: `{vec['id'][:8]}`] {tags_str} (Релевантность: {vec['score']:.2f})\n{vec['text']}"
                )

        return (
            "## RELEVANT INFORMATION (Vector-Graph RAG: Автоматически найденная информация)\n\n"
            + "\n\n".join(blocks)
        )
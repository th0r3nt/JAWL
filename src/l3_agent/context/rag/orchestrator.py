"""
Orchestrator of Hybrid Search (Vector-Graph RAG).

Executes the iterative lookup cycle (Depth Limit N):
1. Resolves search queries and matches graph nodes.
2. Queries VectorDB and GraphDB in parallel.
3. Implements asymmetric semantic mapping: extracts graph nodes from retrieved vector documents,
   and uses descriptions of matched graph nodes as subsequent vector queries.
"""

from typing import List, Dict, Any, Set

from src.utils.logger import main_logger, agent_logger
from src.utils.settings import RAGConfig

from src.l1_databases.vector.embedding import EmbeddingModel
from src.l3_agent.context.rag.entity_extractor import EntityExtractor
from src.l3_agent.context.rag.search.vector import VectorSearchWrapper
from src.l3_agent.context.rag.search.graph import GraphSearchWrapper


class GraphRAGOrchestrator:
    """Core of the hybrid RAG algorithm."""

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
        Executes the hybrid search cycle for an array of input text triggers.

        Args:
            input_texts: Array of active text strings (thoughts, user inputs).

        Returns:
            str: Compiled and formatted Markdown block.
        """

        if not input_texts:
            return ""

        vocab = await self.graph_search.get_all_node_names()
        self.extractor.build_graph_vocabulary(vocab)

        visited_vector_queries: Set[str] = set()
        visited_graph_nodes: Set[str] = set()

        all_vector_results: Dict[str, Dict[str, Any]] = {}
        all_graph_results: Dict[str, Dict[str, Any]] = {}

        current_vector_queries: Set[str] = set()
        current_graph_nodes: Set[str] = set()

        for text in input_texts:
            current_vector_queries.update(self.extractor.extract_vector_queries(text))
            current_graph_nodes.update(self.extractor.extract_graph_nodes(text))

        log = f"[Vector-Graph RAG] Extracted: {len(current_vector_queries)} vector anchors, {len(current_graph_nodes)} graph nodes."
        agent_logger.info(log)

        for depth in range(self.config.depth_limit):
            current_vector_queries -= visited_vector_queries
            current_graph_nodes -= visited_graph_nodes

            if not current_vector_queries and not current_graph_nodes:
                main_logger.debug(
                    f"[GraphRAG] Early Exit at depth {depth} (no new search anchors)."
                )
                break

            visited_vector_queries.update(current_vector_queries)
            visited_graph_nodes.update(current_graph_nodes)

            # -----------------------------------------------------------------
            # I/O: Querying both databases
            # -----------------------------------------------------------------

            vector_results = []
            if current_vector_queries:
                embeddings = await self.embedding_model.get_embeddings_batch(
                    list(current_vector_queries)
                )
                vector_results = await self.vector_search.search_batch(embeddings)

            graph_results = []
            if current_graph_nodes:
                graph_results = await self.graph_search.get_nodes_with_neighborhood(
                    list(current_graph_nodes)
                )

            # -----------------------------------------------------------------
            # Context cross-synchronization
            # -----------------------------------------------------------------

            new_vector_queries: Set[str] = set()
            new_graph_nodes: Set[str] = set()

            for v_res in vector_results:
                v_id = v_res["id"]
                if (
                    v_id not in all_vector_results
                    or v_res["score"] > all_vector_results[v_id]["score"]
                ):
                    all_vector_results[v_id] = v_res

                extracted_nodes = self.extractor.extract_graph_nodes(v_res["text"])
                new_graph_nodes.update(extracted_nodes)

            for g_res in graph_results:
                g_name = g_res["name"]
                if g_name not in all_graph_results:
                    all_graph_results[g_name] = g_res

                desc = g_res["description"]
                if desc:
                    extracted_queries = self.extractor.extract_vector_queries(desc)
                    new_vector_queries.update(extracted_queries)

            current_vector_queries = new_vector_queries
            current_graph_nodes = new_graph_nodes

        return self._format_markdown(all_vector_results, all_graph_results)

    def _format_markdown(
        self,
        vector_results: Dict[str, Dict[str, Any]],
        graph_results: Dict[str, Dict[str, Any]],
    ) -> str:
        """Sorts, trims to set limits, and formats results into Markdown."""

        sorted_vectors = sorted(
            vector_results.values(), key=lambda x: x["score"], reverse=True
        )
        top_vectors = sorted_vectors[: self.config.max_vector_blocks]

        top_graph = list(graph_results.values())[: self.config.max_graph_nodes]

        if not top_vectors and not top_graph:
            return ""

        blocks = []

        if top_graph:
            blocks.append("### Connection Map:")
            for node in top_graph:
                rels = (
                    "\n    ".join(node["relations"])
                    if node["relations"]
                    else "    (no relations)"
                )
                blocks.append(
                    f"- Node: {node['name']} (Type: {node['category']})\n"
                    f"  Description: {node['description']}\n"
                    f"  Relations:\n    {rels}"
                )

        if top_vectors:
            blocks.append("\n### Memories:")
            for vec in top_vectors:
                tags_str = f"[{', '.join(vec['tags'])}]" if vec["tags"] else "[No tags]"
                src_str = f" [Source: {vec.get('source', 'Internal monologue')}]"
                rel_str = f" [Reliability: {vec.get('reliability', 'assumption')}]"
                blocks.append(
                    f"[ID: `{vec['id'][:8]}`]{src_str}{rel_str} {tags_str} (Relevance: {vec['score']:.2f})\n{vec['text']}"
                )

        return (
            "## RELEVANT INFORMATION (Vector-Graph RAG: Automatically retrieved information)\n\n"
            + "\n\n".join(blocks)
        )

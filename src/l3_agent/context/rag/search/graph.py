"""
Graph Database Search Wrapper (KuzuDB).

Provides semantic resolving. Fetches node properties and crawls adjacent edges
safely to bypass combinatorial neighbors explosion.
"""

import json
import asyncio
from typing import List, Dict, Any

from src.utils.logger import main_logger
from src.l1_databases.graph.manager import GraphManager
from src.l1_databases.graph.schema import GRAPH_NODE_TABLE, GRAPH_EDGE_TABLES


class GraphSearchWrapper:
    """Standardized knowledge graph query wrapper."""

    def __init__(self, graph_manager: GraphManager, max_neighbors: int = 15) -> None:
        """
        Args:
            graph_manager: Graph manager.
            max_neighbors: Hard ceiling limit for outgoing/incoming adjacent edges.
        """

        self.graph = graph_manager
        self.max_neighbors = max_neighbors

    async def get_all_node_names(self) -> List[str]:
        """
        Dumps names of all existing graph nodes.
        Used to feed the Aho-Corasick vocabulary.
        """

        if not self.graph.db.conn:
            return []

        def _fetch_names() -> List[str]:
            names = []
            try:
                res = self.graph.db.conn.execute(f"MATCH (n:{GRAPH_NODE_TABLE}) RETURN n.name")
                while res.has_next():
                    names.append(res.get_next()[0])
            except Exception as e:
                main_logger.error(f"[GraphRAG] Error fetching node names: {e}")
            return names

        return await asyncio.to_thread(_fetch_names)

    async def get_nodes_with_neighborhood(self, node_names: List[str]) -> List[Dict[str, Any]]:
        """
        Extracts node properties and maps adjacent relations.

        Args:
            node_names: Exact matched node names.

        Returns:
            List[Dict[str, Any]]: List of populated node dicts.
        """

        if not self.graph.db.conn or not node_names:
            return []

        def _fetch_neighborhood() -> List[Dict[str, Any]]:
            results = []

            for name in node_names:
                safe_name = json.dumps(name, ensure_ascii=False)

                try:
                    node_q = f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) RETURN n.description, n.category, n.is_active"
                    res = self.graph.db.conn.execute(node_q)

                    if not res.has_next():
                        continue

                    row = res.get_next()
                    while res.has_next():
                        res.get_next()

                    desc, cat, is_active = row[0], row[1], row[2]

                    if not is_active:
                        continue

                    node_data = {
                        "name": name,
                        "description": desc,
                        "category": cat,
                        "relations": [],
                    }

                    for rel in GRAPH_EDGE_TABLES:
                        # Outgoing
                        q_out = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_name}}})-[e:{rel}]->(b:{GRAPH_NODE_TABLE}) WHERE b.is_active = true RETURN b.name LIMIT {self.max_neighbors}"
                        res_out = self.graph.db.conn.execute(q_out)
                        while res_out.has_next():
                            target = res_out.get_next()[0]
                            node_data["relations"].append(f"-[{rel}]-> ({target})")

                        # Incoming
                        q_in = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_name}}})<-[e:{rel}]-(b:{GRAPH_NODE_TABLE}) WHERE b.is_active = true RETURN b.name LIMIT {self.max_neighbors}"
                        res_in = self.graph.db.conn.execute(q_in)
                        while res_in.has_next():
                            source = res_in.get_next()[0]
                            node_data["relations"].append(f"<-[{rel}]- from ({source})")

                    results.append(node_data)

                except Exception as e:
                    main_logger.error(
                        f"[GraphRAG] Error extracting neighborhood for '{name}': {e}"
                    )

            return results

        async with self.graph.db.write_lock:
            return await asyncio.to_thread(_fetch_neighborhood)

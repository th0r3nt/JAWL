import asyncio
import json
from typing import List, Dict, Any

from src.utils.logger import main_logger
from src.l1_databases.graph.db import GraphDB
from src.l1_databases.graph.schema import (
    CODE_NODE_TABLE,
    CODE_EDGE_TABLES,
    CodeNodeType,
    CodeRelationType,
)


class GraphASTCRUD:
    """Low-level controller for managing AST nodes in the graph database."""

    def __init__(self, db: GraphDB) -> None:
        self.db = db

    async def upsert_node(
        self, node_id: str, name: str, node_type: CodeNodeType, file_path: str, project_id: str
    ) -> None:
        """
        Adds or updates a code node.
        """

        async with self.db.write_lock:

            def _sync() -> None:
                # Cypher Injection protection (KuzuDB crashes on quotes)
                s_id = json.dumps(node_id, ensure_ascii=False)
                s_name = json.dumps(name, ensure_ascii=False)
                s_type = json.dumps(node_type, ensure_ascii=False)
                s_path = json.dumps(file_path, ensure_ascii=False)
                s_proj = json.dumps(project_id, ensure_ascii=False)

                check_q = f"MATCH (n:{CODE_NODE_TABLE} {{id: {s_id}}}) RETURN n.id"
                res = self.db.conn.execute(check_q)
                exists = res.has_next()
                while res.has_next():
                    res.get_next()

                if exists:
                    self.db.conn.execute(
                        f"MATCH (n:{CODE_NODE_TABLE} {{id: {s_id}}}) "
                        f"SET n.name={s_name}, n.type={s_type}, n.file_path={s_path}, n.project_id={s_proj}"
                    )
                else:
                    self.db.conn.execute(
                        f"CREATE (n:{CODE_NODE_TABLE} {{id: {s_id}, name: {s_name}, type: {s_type}, "
                        f"file_path: {s_path}, project_id: {s_proj}}})"
                    )

            await asyncio.to_thread(_sync)

    async def link_nodes(
        self, source_id: str, target_id: str, relation: CodeRelationType
    ) -> None:
        """
        Links two nodes (e.g., FILE -> IMPORTS -> FILE).
        """

        async with self.db.write_lock:

            def _sync() -> None:
                s_src = json.dumps(source_id, ensure_ascii=False)
                s_tgt = json.dumps(target_id, ensure_ascii=False)

                # Verify if such relation already exists
                check_q = f"MATCH (a:{CODE_NODE_TABLE} {{id: {s_src}}})-[e:{relation}]->(b:{CODE_NODE_TABLE} {{id: {s_tgt}}}) RETURN e"
                res = self.db.conn.execute(check_q)
                if res.has_next():
                    while res.has_next():
                        res.get_next()
                    return

                create_q = f"""
                MATCH (a:{CODE_NODE_TABLE} {{id: {s_src}}}), (b:{CODE_NODE_TABLE} {{id: {s_tgt}}})
                CREATE (a)-[e:{relation}]->(b)
                """
                self.db.conn.execute(create_q)

            await asyncio.to_thread(_sync)

    async def get_dependencies(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Returns nodes that the passed node depends on (outgoing relations).
        """
        return await self._get_edges(node_id, direction="out")

    async def get_usages(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Returns nodes that use the passed node (incoming relations - who depends on us).
        """
        return await self._get_edges(node_id, direction="in")

    async def _get_edges(self, node_id: str, direction: str) -> List[Dict[str, Any]]:
        """
        Helper method to extract relations.
        """

        async with self.db.write_lock:

            def _sync() -> List[Dict[str, Any]]:
                s_id = json.dumps(node_id, ensure_ascii=False)
                results = []

                for rel in CODE_EDGE_TABLES:
                    if direction == "out":
                        q = f"MATCH (a:{CODE_NODE_TABLE} {{id: {s_id}}})-[e:{rel}]->(b:{CODE_NODE_TABLE}) RETURN b.id, b.name, b.type, b.file_path"
                    else:
                        q = f"MATCH (a:{CODE_NODE_TABLE} {{id: {s_id}}})<-[e:{rel}]-(b:{CODE_NODE_TABLE}) RETURN b.id, b.name, b.type, b.file_path"

                    res = self.db.conn.execute(q)
                    while res.has_next():
                        row = res.get_next()
                        results.append(
                            {
                                "relation": rel,
                                "id": row[0],
                                "name": row[1],
                                "type": row[2],
                                "file_path": row[3],
                            }
                        )
                return results

            return await asyncio.to_thread(_sync)

    async def delete_project(self, project_id: str) -> None:
        """
        Deletes all nodes and relations belonging to a specific project.
        """

        async with self.db.write_lock:

            def _sync() -> None:
                s_proj = json.dumps(project_id, ensure_ascii=False)

                # KuzuDB lacks DETACH DELETE, so we remove all relations manually
                for rel in CODE_EDGE_TABLES:
                    # Outgoing
                    self.db.conn.execute(
                        f"MATCH (n:{CODE_NODE_TABLE} {{project_id: {s_proj}}})-[e:{rel}]->() DELETE e"
                    )
                    # Incoming
                    self.db.conn.execute(
                        f"MATCH (n:{CODE_NODE_TABLE} {{project_id: {s_proj}}})<-[e:{rel}]-() DELETE e"
                    )

                # Then remove the nodes themselves
                self.db.conn.execute(
                    f"MATCH (n:{CODE_NODE_TABLE} {{project_id: {s_proj}}}) DELETE n"
                )

                main_logger.info(f"[Graph DB] AST project '{project_id}' completely deleted.")

            await asyncio.to_thread(_sync)

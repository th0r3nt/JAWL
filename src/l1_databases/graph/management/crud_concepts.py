"""
CRUD controller for working with the Knowledge Graph.

Implements skills for adding and linking concepts.
Includes Entity Resolution magic (fuzzy matching) and idempotent queries
protected against KuzuDB parser bugs via literal serialization (json.dumps).
"""

import asyncio
import json
from typing import List, Optional
from rapidfuzz import process, fuzz

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents
from src.l3_agent.subconscious.schema import Pattern

from src.l1_databases.graph.db import GraphDB
from src.l1_databases.graph.schema import (
    GRAPH_NODE_TABLE,
    GRAPH_EDGE_TABLES,
    RelationType,
    ConceptCategory,
)


class GraphCRUD:
    """Agent interface to the knowledge graph."""

    def __init__(self, db: GraphDB, max_nodes: int = 5000) -> None:
        self.db = db
        self.max_nodes = max_nodes

    def _get_all_names(self) -> List[str]:
        """Returns names of all existing nodes in the graph."""
        if not self.db.conn:
            return []

        res = self.db.conn.execute(f"MATCH (n:{GRAPH_NODE_TABLE}) RETURN n.name")
        names = []
        while res.has_next():
            names.append(res.get_next()[0])
        return names

    def _fuzzy_match(self, entity_name: str, threshold: float = 85.0) -> str:
        """
        Entity Resolution magic: searches for a similar node name in the graph.
        If found with similarity > threshold, returns the existing name.
        If not, returns the original name (a new node will be created).
        """
        existing_nodes = self._get_all_names()
        if not existing_nodes:
            return entity_name.strip()

        # Use processor to compare strings in lower case.
        # This saves from issues where "Docker" and "docker" yield a score of 83.3% and fail the 85% threshold.
        match = process.extractOne(
            entity_name.strip(),
            existing_nodes,
            processor=lambda x: x.lower() if isinstance(x, str) else x,
            scorer=fuzz.WRatio,
        )

        if match:
            best_name, score, _ = match
            if score >= threshold:
                main_logger.debug(
                    f"[Graph DB] Fuzzy Match: '{entity_name}' -> '{best_name}' (Score: {score:.1f})"
                )
                return best_name

        return entity_name.strip()

    @skill(
        swarm=[Subagents.ARCHIVIST, Subagents.WEB_RESEARCHER],
        subconscious=[Pattern.CONSOLIDATION],
    )
    async def add_concept(
        self, name: str, description: str, category: ConceptCategory = "CONCEPT"
    ) -> SkillResult:
        """
        Adds a new or updates an existing concept node in the Knowledge Graph.
        """
        
        async with self.db.write_lock:

            def _sync_manage() -> str:
                # Resolve name (threshold 85 - default for Upsert)
                resolved_name = self._fuzzy_match(name, threshold=85.0)

                # Bulletproof protection against Cypher Injection and Kuzu parser bugs
                safe_name = json.dumps(resolved_name, ensure_ascii=False)
                safe_desc = json.dumps(description, ensure_ascii=False)
                safe_cat = json.dumps(category, ensure_ascii=False)

                check_q = f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) RETURN n.name"
                res = self.db.conn.execute(check_q)
                exists = res.has_next()

                # Must consume the iterator to release the KuzuDB Read Lock on the record!
                while res.has_next():
                    res.get_next()

                if exists:
                    # Update. Add RETURN so KuzuDB is guaranteed to persist the SET
                    update_q = f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) SET n.description = {safe_desc}, n.category = {safe_cat}, n.is_active = true RETURN n.name"
                    res_upd = self.db.conn.execute(update_q)
                    while res_upd.has_next():
                        res_upd.get_next()
                else:
                    # Create. Add RETURN
                    create_q = f"CREATE (n:{GRAPH_NODE_TABLE} {{name: {safe_name}, description: {safe_desc}, category: {safe_cat}, is_active: true}}) RETURN n.name"
                    res_crt = self.db.conn.execute(create_q)
                    while res_crt.has_next():
                        res_crt.get_next()

                return resolved_name

            try:
                final_name = await asyncio.to_thread(_sync_manage)
                msg = f"Concept '{final_name}' (Type: {category}) saved to graph."
                main_logger.info(f"[Graph DB] {msg}")
                return SkillResult.ok("True")
            except Exception as e:
                return SkillResult.fail(f"Database error: {e}")

    @skill(
        swarm=[Subagents.ARCHIVIST, Subagents.WEB_RESEARCHER],
        subconscious=[Pattern.CONSOLIDATION],
    )
    async def link_concepts(
        self, source_name: str, target_name: str, relation: RelationType, description: str = ""
    ) -> SkillResult:
        """
        Creates a relation edge between two graph nodes. Missing nodes are auto-created.
        """

        if relation not in GRAPH_EDGE_TABLES:
            return SkillResult.fail(f"Unknown relationship type: {relation}")

        async with self.db.write_lock:

            def _sync_link() -> str:
                src = self._fuzzy_match(source_name, threshold=85.0)
                tgt = self._fuzzy_match(target_name, threshold=85.0)

                safe_src = json.dumps(src, ensure_ascii=False)
                safe_tgt = json.dumps(tgt, ensure_ascii=False)
                safe_desc = json.dumps(description, ensure_ascii=False)

                # Ensure nodes exist
                for n_name, s_name in [(src, safe_src), (tgt, safe_tgt)]:
                    res = self.db.conn.execute(
                        f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {s_name}}}) RETURN n.name"
                    )
                    exists = res.has_next()
                    while res.has_next():
                        res.get_next()

                    if not exists:
                        res_crt = self.db.conn.execute(
                            f"CREATE (n:{GRAPH_NODE_TABLE} {{name: {s_name}, is_active: true}}) RETURN n.name"
                        )
                        while res_crt.has_next():
                            res_crt.get_next()

                # Check for duplicates
                check_q = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_src}}})-[e:{relation}]->(b:{GRAPH_NODE_TABLE} {{name: {safe_tgt}}}) RETURN e"
                res = self.db.conn.execute(check_q)
                has_edge = res.has_next()
                while res.has_next():
                    res.get_next()

                if not has_edge:
                    create_q = f"""
                    MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_src}}}), (b:{GRAPH_NODE_TABLE} {{name: {safe_tgt}}})
                    CREATE (a)-[e:{relation} {{description: {safe_desc}}}]->(b)
                    RETURN e.description
                    """
                    res_edge = self.db.conn.execute(create_q)
                    while res_edge.has_next():
                        res_edge.get_next()

                return f"({src}) -[{relation}]-> ({tgt})"

            try:
                link_str = await asyncio.to_thread(_sync_link)
                msg = f"Relation updated: {link_str}"
                main_logger.info(f"[Graph DB] {msg}")
                return SkillResult.ok("True")
            except Exception as e:
                return SkillResult.fail(f"Error linking: {e}")

    @skill(
        swarm=[Subagents.ARCHIVIST, Subagents.WEB_RESEARCHER],
        subconscious=[Pattern.CONSOLIDATION, Pattern.REFLECTION],
    )
    async def get_concept_neighborhood(self, name: str) -> SkillResult:
        """
        Searches for a graph node by name and returns its description and all relations.
        """

        def _sync_explore() -> str:
            # Threshold 75 for more aggressive search during queries
            resolved_name = self._fuzzy_match(name, threshold=75.0)
            safe_name = json.dumps(resolved_name, ensure_ascii=False)

            res = self.db.conn.execute(
                f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) RETURN n.description, n.category, n.is_active"
            )
            if not res.has_next():
                return f"Node similar to '{name}' not found in the graph."

            row = res.get_next()
            # Clear result (release lock)
            while res.has_next():
                res.get_next()

            desc, cat, is_active = row[0], row[1], row[2]

            if not is_active:
                return f"Concept '{resolved_name}' was archived."

            lines = [
                f"### Concept: {resolved_name} (Type: {cat})\nDescription: {desc}\n\nRelations:"
            ]
            found_edges = False

            # Search for relations in all relationship tables
            for rel in GRAPH_EDGE_TABLES:
                # OUTGOING
                q_out = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_name}}})-[e:{rel}]->(b:{GRAPH_NODE_TABLE}) WHERE b.is_active = true RETURN b.name, e.description"
                res_out = self.db.conn.execute(q_out)
                while res_out.has_next():
                    found_edges = True
                    r = res_out.get_next()
                    e_desc = f" ({r[1]})" if r[1] else ""
                    lines.append(f"  -[{rel}]-> ({r[0]}){e_desc}")

                # INCOMING
                q_in = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_name}}})<-[e:{rel}]-(b:{GRAPH_NODE_TABLE}) WHERE b.is_active = true RETURN b.name, e.description"
                res_in = self.db.conn.execute(q_in)
                while res_in.has_next():
                    found_edges = True
                    r = res_in.get_next()
                    e_desc = f" ({r[1]})" if r[1] else ""
                    lines.append(f"  <-[{rel}]- of ({r[0]}){e_desc}")

            if not found_edges:
                lines.append("  (Isolated node, no active relations)")

            return "\n".join(lines)

        try:
            report = await asyncio.to_thread(_sync_explore)
            return SkillResult.ok(report)
        except Exception as e:
            return SkillResult.fail(f"Error exploring graph: {e}")

    @skill(
        swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.FORGETTING, Pattern.CONSOLIDATION]
    )
    async def remove_link(
        self, source_name: str, target_name: str, relation: Optional[RelationType] = None
    ) -> SkillResult:
        """
        Removes link(s) between two graph nodes.
        """

        async with self.db.write_lock:

            def _sync_remove_link() -> str:
                # Threshold 95% to avoid accidental deletion of similar-sounding relations
                src = self._fuzzy_match(source_name, threshold=95.0)
                tgt = self._fuzzy_match(target_name, threshold=95.0)

                safe_src = json.dumps(src, ensure_ascii=False)
                safe_tgt = json.dumps(tgt, ensure_ascii=False)

                rels_to_check = [relation] if relation else GRAPH_EDGE_TABLES

                for rel in rels_to_check:
                    # KuzuDB does not support deleting undirected edges, so we delete in both directions explicitly with RETURN
                    q_out = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_src}}})-[e:{rel}]->(b:{GRAPH_NODE_TABLE} {{name: {safe_tgt}}}) DELETE e RETURN a.name"
                    res_out = self.db.conn.execute(q_out)
                    while res_out.has_next():
                        res_out.get_next()

                    q_in = f"MATCH (a:{GRAPH_NODE_TABLE} {{name: {safe_src}}})<-[e:{rel}]-(b:{GRAPH_NODE_TABLE} {{name: {safe_tgt}}}) DELETE e RETURN a.name"
                    res_in = self.db.conn.execute(q_in)
                    while res_in.has_next():
                        res_in.get_next()

                return f"Relations between '{src}' and '{tgt}' were deleted."

            try:
                msg = await asyncio.to_thread(_sync_remove_link)
                main_logger.info(f"[Graph DB] {msg}")
                return SkillResult.ok("True")
            except Exception as e:
                return SkillResult.fail(f"Error deleting relation: {e}")

    @skill(swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.FORGETTING])
    async def erase_concept(self, name: str) -> SkillResult:
        """
        Fully erases a concept node and its relations from the database.
        """

        async with self.db.write_lock:

            def _sync_erase() -> str:
                # Threshold 95% to prevent accidental wipe of half the database
                resolved_name = self._fuzzy_match(name, threshold=95.0)
                safe_name = json.dumps(resolved_name, ensure_ascii=False)

                check_q = f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) RETURN n.name"
                res = self.db.conn.execute(check_q)
                exists = res.has_next()
                while res.has_next():
                    res.get_next()

                if not exists:
                    return f"Node '{name}' not found."

                # First wipe all relations explicitly in both directions
                for rel in GRAPH_EDGE_TABLES:
                    res_e1 = self.db.conn.execute(
                        f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}})-[e:{rel}]->() DELETE e RETURN n.name"
                    )
                    while res_e1.has_next():
                        res_e1.get_next()

                    res_e2 = self.db.conn.execute(
                        f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}})<-[e:{rel}]-() DELETE e RETURN n.name"
                    )
                    while res_e2.has_next():
                        res_e2.get_next()

                # Now delete the node itself
                res_del = self.db.conn.execute(
                    f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) DELETE n RETURN n.name"
                )
                while res_del.has_next():
                    res_del.get_next()

                return f"Node '{resolved_name}' and all its relations have been physically destroyed."

            try:
                msg = await asyncio.to_thread(_sync_erase)
                main_logger.info(f"[Graph DB] {msg}")
                return SkillResult.ok("True")
            except Exception as e:
                return SkillResult.fail(f"Error during hard deletion: {e}")

    @skill(swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.FORGETTING])
    async def archive_concept(self, name: str) -> SkillResult:
        """
        Performs soft deletion. Hides the node from search and graph, but keeps it in the database.
        """

        async with self.db.write_lock:

            def _sync_archive() -> bool:
                resolved_name = self._fuzzy_match(name, threshold=95.0)
                safe_name = json.dumps(resolved_name, ensure_ascii=False)

                res = self.db.conn.execute(
                    f"MATCH (n:{GRAPH_NODE_TABLE} {{name: {safe_name}}}) SET n.is_active = false RETURN n.name"
                )
                exists = res.has_next()
                while res.has_next():
                    res.get_next()
                return exists

            try:
                success = await asyncio.to_thread(_sync_archive)
                if success:
                    return SkillResult.ok("True")
                return SkillResult.fail(f"Concept '{name}' not found.")
            except Exception as e:
                return SkillResult.fail(f"Error during archivation: {e}")

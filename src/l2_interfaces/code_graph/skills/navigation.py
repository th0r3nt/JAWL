"""
Skills for navigating in Code Graphs.

Code graphs store dependencies, descriptions, and help understand complex codebases,
thanks to semantic vector search over relations in a deterministic graph.
"""

from typing import Optional

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l2_interfaces.code_graph.client import CodeGraphClient
from src.l1_databases.graph.management.crud_ast import GraphASTCRUD
from src.l1_databases.vector.management.code_ast import VectorCodeAST


class CodeGraphNavigation:
    """
    Skills for instant search and relationship analysis in code (Agentic Introspection).
    """

    def __init__(
        self, client: CodeGraphClient, graph_crud: GraphASTCRUD, vector_crud: VectorCodeAST
    ):
        self.client = client
        self.graph = graph_crud
        self.vector = vector_crud

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER])
    async def search_code_semantic(
        self, project_id: str, query: str, limit: Optional[int] = None
    ) -> SkillResult:
        """
        Semantic search over docstrings. Useful when function purpose is known but name isn't.

        query: Semantic text query.
        """

        if project_id not in self.client.state.active_indexes:
            return SkillResult.fail(
                f"Project '{project_id}' not found. Please index it first."
            )

        try:
            search_limit = (
                limit if limit is not None else self.client.config.max_search_results
            )
            results = await self.vector.search(query, project_id, search_limit)

            if not results:
                return SkillResult.ok(f"No matches found for semantic query '{query}'.")

            lines = [f"Semantic search results for ('{query}'):"]
            for r in results:
                # Parse node ID: 'project_id::src/file.py::ClassName' -> take only 'src/file.py::ClassName'
                clean_id = r["node_id"].replace(f"{project_id}::", "")
                desc = r["text"].replace("\n", " ")
                # Truncate docstring for output
                desc = desc[:150] + "..." if len(desc) > 150 else desc

                lines.append(
                    f"- [{r['type']}] `{clean_id}` (Similarity: {r['score']:.2f})\n  Docstring: {desc}"
                )

            main_logger.info(f"[Code Graph] Semantic search for '{query}' completed.")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Semantic search error: {e}")

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER])
    async def trace_dependencies(self, project_id: str, target_name: str) -> SkillResult:
        """
        Blast radius search. Shows where target is imported or class contents.

        target_name: Filename or class path (e.g., 'src/main.py::MyClass').
        """

        if project_id not in self.client.state.active_indexes:
            return SkillResult.fail(f"Project '{project_id}' not found.")

        node_id = f"{project_id}::{target_name}"

        # Mapping of relations to human language for better agent understanding
        def format_relation(rel_type: str, direction: str) -> str:
            mapping = {
                "in": {
                    "IMPORTS": "Imported by",
                    "CONTAINS": "Contained within",
                    "DEFINES": "Defined by",
                    "CALLS": "Called by",
                },
                "out": {
                    "IMPORTS": "Imports",
                    "CONTAINS": "Contains",
                    "DEFINES": "Defines",
                    "CALLS": "Calls",
                },
            }
            return mapping.get(direction, {}).get(rel_type, f"[{rel_type}] is linked to")

        try:
            # Incoming relations (who depends on us)
            usages = await self.graph.get_usages(node_id)
            # Outgoing relations (what we depend on)
            deps = await self.graph.get_dependencies(node_id)

            if not usages and not deps:
                return SkillResult.ok(
                    f"Node '{target_name}' not found in the graph or has no relations."
                )

            lines = [f"Architectural relations for `{target_name}`:\n"]

            if usages:
                lines.append("Who uses this node (Depends on it):")
                for u in usages:
                    clean_id = u["id"].replace(f"{project_id}::", "")
                    rel_text = format_relation(u["relation"], "in")
                    lines.append(f"  - {rel_text}: {clean_id} ({u['type']})")

            if deps:
                lines.append("\nWhat uses this node (It depends on them):")
                for d in deps:
                    clean_id = d["id"].replace(f"{project_id}::", "")
                    rel_text = format_relation(d["relation"], "out")
                    lines.append(f"  - {rel_text}: {clean_id} ({d['type']})")

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error searching dependencies: {e}")

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER])
    async def get_file_structure(self, project_id: str, filepath: str) -> SkillResult:
        """
        Instantly returns file classes/methods without full code read.

        filepath: Relative path (e.g., 'src/main.py').
        """

        if project_id not in self.client.state.active_indexes:
            return SkillResult.fail(f"Project '{project_id}' not found.")

        file_node_id = f"{project_id}::{filepath}"

        try:
            # Search for everything contained in the file (CONTAINS relationships)
            contents = await self.graph.get_dependencies(file_node_id)

            if not contents:
                return SkillResult.ok(
                    f"File '{filepath}' is empty, does not contain classes/functions, or is not indexed."
                )

            limit = self.client.config.max_structure_items
            lines = [f"Structure of file `{filepath}` (Display limit: {limit}):"]
            count = 0

            for item in contents:
                if count >= limit:
                    lines.append("- ... [Remaining elements hidden to save context]")
                    break

                if item["relation"] == "CONTAINS":
                    clean_name = item["id"].replace(f"{project_id}::{filepath}::", "")
                    count += 1
                    lines.append(f"- [{item['type']}] {clean_name}")

                    # If it is a class, search for its methods (DEFINES relationship)
                    if item["type"] == "CLASS":
                        methods = await self.graph.get_dependencies(item["id"])
                        for m in methods:
                            if m["relation"] == "DEFINES":
                                m_name = m["id"].split(".")[-1]
                                lines.append(f"    - [METHOD] {m_name}")

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error retrieving file structure: {e}")

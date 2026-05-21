"""
Facade for the graph memory layer (KuzuDB).

Encapsulates database startup/shutdown logic and provides access to CRUD skills.
"""

from pathlib import Path
from src.l1_databases.graph.db import GraphDB
from src.l1_databases.graph.management.crud_concepts import GraphCRUD
from src.l1_databases.graph.management.crud_ast import GraphASTCRUD


class GraphManager:
    """Graph database orchestrator."""

    def __init__(self, db_path: Path, max_nodes: int = 5000) -> None:
        self.db = GraphDB(db_path=str(db_path))
        self.crud = GraphCRUD(db=self.db, max_nodes=max_nodes)
        self.ast_crud = GraphASTCRUD(db=self.db)

    async def connect(self) -> None:
        """
        Opens connection and initializes the KuzuDB schema.
        """

        await self.db.connect()

    async def disconnect(self) -> None:
        """
        Safely closes the connection.
        """

        await self.db.disconnect()

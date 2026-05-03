"""
Фасад для слоя графовой памяти (KuzuDB).

Инкапсулирует логику запуска/остановки базы и предоставляет доступ к CRUD навыкам.
"""

from pathlib import Path
from src.l1_databases.graph.db import GraphDB
from src.l1_databases.graph.management.crud_concepts import GraphCRUD
from src.l1_databases.graph.management.crud_ast import GraphASTCRUD


class GraphManager:
    """Оркестратор графовой базы данных."""

    def __init__(self, db_path: Path, max_nodes: int = 5000) -> None:
        self.db = GraphDB(db_path=str(db_path))
        self.crud = GraphCRUD(db=self.db, max_nodes=max_nodes)
        self.ast_crud = GraphASTCRUD(db=self.db)

    async def connect(self) -> None:
        """Открывает подключение и формирует схему KuzuDB."""
        await self.db.connect()

    async def disconnect(self) -> None:
        """Безопасно закрывает соединение."""
        await self.db.disconnect()
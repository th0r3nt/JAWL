"""
Graph Database (KuzuDB).

Encapsulates the connection, schema management, and provides
a safe execution mechanism for Cypher queries using locks.
"""

import asyncio
from pathlib import Path
import kuzu

from src.utils.logger import main_logger
from src.l1_databases.graph.schema import (
    GRAPH_NODE_TABLE,
    GRAPH_EDGE_TABLES,
    CODE_NODE_TABLE,
    CODE_EDGE_TABLES,
)


class GraphDB:
    """
    Connection and structure manager for the Kuzu graph database.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db: kuzu.Database | None = None
        self.conn: kuzu.Connection | None = None
        self.write_lock = asyncio.Lock()

    async def connect(self) -> None:
        def _init_db() -> None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db = kuzu.Database(str(self.db_path))
            self.conn = kuzu.Connection(self.db)
            self._init_schema()

        try:
            await asyncio.to_thread(_init_db)
            main_logger.info("[Graph DB] Kuzu database successfully initialized.")
        except Exception as e:
            main_logger.error(f"[Graph DB] Critical error starting Kuzu: {e}")
            raise e

    def _init_schema(self) -> None:
        """
        Synchronously verifies and creates the DDL schema based on schema.py.
        Implemented via exception catching to ensure idempotency
        and protect against schema changes of system tables in newer KuzuDB versions.
        """

        if not self.conn:
            return

        # =================================================================
        # MAIN NODE TABLE
        # =================================================================

        try:
            query = f"""
            CREATE NODE TABLE {GRAPH_NODE_TABLE}(
                name STRING, 
                description STRING, 
                category STRING, 
                is_active BOOLEAN, 
                PRIMARY KEY (name)
            )
            """
            self.conn.execute(query)
        except RuntimeError as e:
            # If the table already exists, KuzuDB raises a RuntimeError
            if "already exists" not in str(e).lower():
                raise e

        for edge in GRAPH_EDGE_TABLES:
            try:
                self.conn.execute(
                    f"CREATE REL TABLE {edge}(FROM {GRAPH_NODE_TABLE} TO {GRAPH_NODE_TABLE}, description STRING);"
                )
            except RuntimeError as e:
                if "already exists" not in str(e).lower():
                    raise e

        # =================================================================
        # CODE GRAPH (AST)
        # =================================================================

        try:
            query = f"""
            CREATE NODE TABLE {CODE_NODE_TABLE}(
                id STRING, 
                name STRING, 
                type STRING, 
                file_path STRING, 
                project_id STRING,
                PRIMARY KEY (id)
            )
            """
            self.conn.execute(query)
        except RuntimeError as e:
            if "already exists" not in str(e).lower():
                raise e

        for edge in CODE_EDGE_TABLES:
            try:
                # In AST graphs we do not need a 'description' field for edges, the fact of the relationship is sufficient
                self.conn.execute(
                    f"CREATE REL TABLE {edge}(FROM {CODE_NODE_TABLE} TO {CODE_NODE_TABLE});"
                )
            except RuntimeError as e:
                if "already exists" not in str(e).lower():
                    raise e

    async def disconnect(self) -> None:
        """
        Correctly closes the database and releases file locks (especially for Windows).
        """
        
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

        if self.db:
            # In KuzuDB, the database releases file locks only when the object is deleted
            self.db = None

        main_logger.info("[Graph DB] Connection closed.")

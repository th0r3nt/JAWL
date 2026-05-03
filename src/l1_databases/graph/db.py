"""
Ядро графовой базы данных (KuzuDB).

Инкапсулирует подключение, управление схемой (Schema) и предоставляет
безопасный механизм выполнения Cypher-запросов с использованием блокировок (Lock).
"""

import asyncio
from pathlib import Path
import kuzu

from src.utils.logger import system_logger
from src.l1_databases.graph.schema import (
    GRAPH_NODE_TABLE,
    GRAPH_EDGE_TABLES,
    CODE_NODE_TABLE,
    CODE_EDGE_TABLES,
)


class GraphDB:
    """Менеджер подключения и структуры графовой БД Kuzu."""

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
            system_logger.info("[Graph DB] База данных Kuzu успешно инициализирована.")
        except Exception as e:
            system_logger.error(f"[Graph DB] Критическая ошибка при запуске Kuzu: {e}")
            raise e

    def _init_schema(self) -> None:
        """
        Синхронно проверяет и создает DDL схему на основе schema.py.
        Реализовано через перехват исключений для обеспечения идемпотентности
        и защиты от изменения структуры системных таблиц в новых версиях KuzuDB.
        """

        if not self.conn:
            return

        # =================================================================
        # ОСНОВНАЯ ТАБЛИЦА УЗЛОВ
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
            # Если таблица уже существует, KuzuDB выбрасывает RuntimeError
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
                # В AST графах нам не нужно поле 'description' для связей, достаточно самого факта связи
                self.conn.execute(
                    f"CREATE REL TABLE {edge}(FROM {CODE_NODE_TABLE} TO {CODE_NODE_TABLE});"
                )
            except RuntimeError as e:
                if "already exists" not in str(e).lower():
                    raise e

    async def disconnect(self) -> None:
        """Корректно закрывает базу данных и освобождает локи файлов (особенно для Windows)."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

        if self.db:
            # В KuzuDB база освобождает блокировку файлов только при удалении объекта
            self.db = None

        system_logger.info("[Graph DB] Подключение закрыто.")

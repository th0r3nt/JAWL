"""
Relational Database Initialization Module (SQLite).

Low-level wrapper for asynchronous interaction with SQLite.
Manages the connection pool (SQLAlchemy AsyncEngine) and session factory for the entire L1 layer.
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.l1_databases.sql.tables import Base
from src.utils.logger import main_logger


class SQLDB:
    """
    Asynchronous SQLite initialization manager.
    Responsible for creating tables, managing the connection pool, and issuing sessions.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initializes the database engine and session factory.

        Args:
            db_path: Absolute or relative path to the .db file, or ':memory:' for RAM operation.
        """

        # If this is not an in-memory database, ensure the directory exists
        if db_path != ":memory:":
            dir_name = os.path.dirname(db_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

        db_url = f"sqlite+aiosqlite:///{db_path}"

        self.engine = create_async_engine(db_url, echo=False)
        self.session_factory = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def connect(self) -> None:
        """
        Creates a physical connection to SQLite and generates the table schema if they do not exist.
        Must be called strictly once at the start of the system lifecycle.

        Raises:
            Exception: In case of insufficient directory access rights or lock conflicts.
        """

        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            main_logger.info("[SQL DB] Database successfully initialized.")
        except Exception as e:
            main_logger.error(f"[SQL DB] Critical error starting database: {e}")
            raise e

    async def disconnect(self) -> None:
        """
        Safely destroys the connection pool (Engine) and rolls back uncommitted transactions.
        Prevents descriptor leaks (SQLite Database is locked) during system reboot.
        """

        if self.engine:
            await self.engine.dispose()
            main_logger.info("[SQL DB] Connection to the database closed.")

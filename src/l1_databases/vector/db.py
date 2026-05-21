"""
Vector database client (Qdrant).

Provides creation of local In-Memory/On-Disk collections and data corruption
protection. In case of vector dimension changes in the configs,
the system automatically triggers deletion of the old cache to prevent crashes.
"""

import shutil
from pathlib import Path
from typing import List
from qdrant_client import AsyncQdrantClient, models

from src.utils.logger import main_logger


class VectorDB:
    """Connection and structure manager for the Qdrant vector database."""

    def __init__(self, db_path: str, collections: List[str], vector_size: int) -> None:
        """
        Initializes paths and parameters for connection to Qdrant.

        Args:
            db_path: Path to the database files storage directory.
            collections: List of collection names to be created ('knowledge', 'thoughts').
            vector_size: Vector dimension (must strictly match the used embedding model).
        """

        self.db_path = Path(db_path)
        self.client: AsyncQdrantClient | None = None
        self.collections = collections
        self.vector_size = vector_size

    async def connect(self) -> None:
        """
        Establishes connection to the local Qdrant DB.
        Upon first run, automatically creates collections and Payload Index for tags.
        If fatal corruption of the database cache is detected (e.g., due to a change in vector_size) —
        performs a forced Hard Reset (deletes the directory and creates a clean database).

        Raises:
            Exception: If the database cannot be read or recreated.
        """
        self.db_path.mkdir(parents=True, exist_ok=True)

        try:
            self.client = AsyncQdrantClient(path=str(self.db_path))

        except Exception as e:
            if "ValidationError" in str(type(e)) or "CreateCollection" in str(e):
                main_logger.warning(
                    "[Vector DB] Version incompatibility or local DB corruption detected. "
                    "Automatic recovery initiated."
                )
                shutil.rmtree(self.db_path, ignore_errors=True)
                self.db_path.mkdir(parents=True, exist_ok=True)
                self.client = AsyncQdrantClient(path=str(self.db_path))
            else:
                main_logger.error(f"[Vector DB] Critical error starting database: {e}")
                raise e

        # Check and create collections if they do not exist
        for coll in self.collections:
            if not await self.client.collection_exists(coll):
                await self.client.create_collection(
                    collection_name=coll,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
                main_logger.info(f"[Vector DB] Collection created: {coll}")

            # Create KEYWORD index for tags (Qdrant ignores the call if the index already exists)
            # This ensures that search by tags_filter runs in O(1) instead of O(N)
            try:
                await self.client.create_payload_index(
                    collection_name=coll,
                    field_name="tags",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as idx_err:
                main_logger.debug(
                    f"[Vector DB] Index for 'tags' in '{coll}' already exists or an error occurred: {idx_err}"
                )

        main_logger.info(f"[Vector DB] Database initialized at: {self.db_path}")

    async def disconnect(self) -> None:
        """Correctly closes the database on system shutdown and releases File Locks."""
        if self.client:
            try:
                # Explicitly close the client so portalocker releases DB files
                await self.client.close()
            except Exception as e:
                main_logger.debug(f"[Vector DB] Error closing client: {e}")

            self.client = None
            main_logger.info("[Vector DB] Connection to the database closed.")

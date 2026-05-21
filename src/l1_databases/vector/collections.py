"""
Helper module describing vector collections.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB


class VectorCollection:
    """
    Abstraction over a collection (namespace) in Qdrant.
    Allows CRUD modules to work with an isolated partition of the DB.
    """

    def __init__(self, db: "VectorDB", collection_name: str) -> None:
        """
        Initializes a reference to the collection.

        Args:
            db: Reference to the database instance.
            collection_name: Name of the collection (e.g., 'knowledge' or 'thoughts').
        """
        self.db = db
        self.name = collection_name

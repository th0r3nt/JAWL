"""
Служебный модуль описания векторных коллекций.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB


class VectorCollection:
    """
    Абстракция над коллекцией (пространством имен) в Qdrant.
    Позволяет CRUD-модулям работать с изолированным куском БД.
    """

    def __init__(self, db: "VectorDB", collection_name: str) -> None:
        """
        Инициализирует ссылку на коллекцию.

        Args:
            db: Ссылка на инстанс базы данных.
            collection_name: Имя коллекции (например 'knowledge' или 'thoughts').
        """
        self.db = db
        self.name = collection_name

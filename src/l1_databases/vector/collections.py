from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB

class VectorCollection:
    """
    Класс инициализации векторной коллекции.
    """
    def __init__(self, db: 'VectorDB', collection_name: str):
        self.db = db
        self.name = collection_name
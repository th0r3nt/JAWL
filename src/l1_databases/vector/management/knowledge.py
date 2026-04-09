from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.l1_databases.vector.db import VectorDB
    from src.l1_databases.vector.collections import VectorCollection

# TODO: строго через DI


class VectorKnowledge:
    """
    CRUD-функции для взаимодействия с коллекцией знаний агента.
    """

    def __init__(self, db: VectorDB, collection: VectorCollection):
        self.db = db
        self.collection = collection

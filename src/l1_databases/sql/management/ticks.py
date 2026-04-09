from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB
    from src.l1_databases.sql.tables import SQLTable

# TODO: строго через DI


class SQLTasks:
    """
    CRUD-функции для взаимодействия с таблицей долгосрочных задач агента.
    """

    def __init__(self, db: SQLDB, table: SQLTable):
        self.db = db
        self.table = table

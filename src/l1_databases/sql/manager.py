from pathlib import Path

from src.l1_databases.sql.db import SQLDB
from src.l1_databases.sql.management.tasks import SQLTasks
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits


class SQLManager:
    """
    Фасад для SQL слоя.
    Инкапсулирует подключение к SQLite и сборку CRUD-обработчиков.
    """

    def __init__(self, db_path: Path):
        # Ядро базы данных
        self.db = SQLDB(db_path=str(db_path))

        # CRUD-интерфейсы
        self.tasks = SQLTasks(db=self.db)
        self.ticks = SQLTicks(db=self.db)
        self.personality_traits = SQLPersonalityTraits(db=self.db)

    async def connect(self):
        """Создает таблицы и открывает пулы соединений."""
        await self.db.connect()

    async def disconnect(self):
        """Корректно закрывает соединения при остановке."""
        await self.db.disconnect()

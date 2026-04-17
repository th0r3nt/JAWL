from pathlib import Path

from src.l1_databases.sql.db import SQLDB
from src.l1_databases.sql.management.tasks import SQLTasks
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits
from src.l1_databases.sql.management.mental_states import SQLMentalStates

class SQLManager:
    """
    Фасад для SQL слоя.
    Инкапсулирует подключение к SQLite и сборку CRUD-обработчиков.
    """

    def __init__(self, db_path: Path, max_mental_state_entities: int = 10):
        self.db = SQLDB(db_path=str(db_path))

        # CRUD-интерфейсы
        self.tasks = SQLTasks(db=self.db)
        self.ticks = SQLTicks(db=self.db)
        self.personality_traits = SQLPersonalityTraits(db=self.db)
        self.mental_states = SQLMentalStates(db=self.db, max_entities=max_mental_state_entities) 

    async def connect(self):
        """Создает таблицы и открывает пулы соединений."""
        await self.db.connect()

    async def disconnect(self):
        """Корректно закрывает соединения при остановке."""
        await self.db.disconnect()

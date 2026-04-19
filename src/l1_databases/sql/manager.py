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

    def __init__(
        self,
        db_path: Path,
        max_mental_state_entities: int = 10,
        ticks_limit: int = 30,
        tick_result_max_chars: int = 5000,
        timezone: int = 0,
    ):
        self.db = SQLDB(db_path=str(db_path))

        # CRUD-интерфейсы
        self.tasks = SQLTasks(db=self.db)

        self.ticks = SQLTicks(
            db=self.db,
            limit=ticks_limit,
            result_max_chars=tick_result_max_chars,
            tz_offset=timezone,
        )

        self.personality_traits = SQLPersonalityTraits(db=self.db)

        self.mental_states = SQLMentalStates(
            db=self.db, max_entities=max_mental_state_entities
        )

    async def connect(self):
        await self.db.connect()

    async def disconnect(self):
        await self.db.disconnect()

from pathlib import Path

from src.l1_databases.sql.db import SQLDB

# Таблицы
from src.l1_databases.sql.management.tasks import SQLTasks
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits
from src.l1_databases.sql.management.mental_states import SQLMentalStates
from src.l1_databases.sql.management.drives import SQLDrives


class SQLManager:
    """
    Фасад для SQL слоя.
    Инкапсулирует подключение к SQLite и сборку CRUD-обработчиков.
    """

    def __init__(
        self,
        # DB
        db_path: Path,
        # Personality Traits
        max_traits: int = 10,
        # Tasks
        max_tasks: int = 15,
        # Ticks
        ticks_limit: int = 30,
        detailed_ticks: int = 2,
        tick_action_max_chars: int = 2000,
        tick_result_max_chars: int = 5000,
        # Mental State
        max_mental_state_entities: int = 10,
        # Drives
        drives_enabled: bool = True,
        default_decay_rate: float = 5.0,
        max_history_drives: int = 3,
        max_custom_drives: int = 5,
        # Время
        timezone: int = 0,
    ):
        self.drives_enabled = drives_enabled
        self.db = SQLDB(db_path=str(db_path))

        # Tasks
        self.tasks = SQLTasks(db=self.db, max_tasks=max_tasks)

        # Ticks
        self.ticks = SQLTicks(
            db=self.db,
            limit=ticks_limit,
            detailed_ticks=detailed_ticks,
            action_max_chars=tick_action_max_chars,
            result_max_chars=tick_result_max_chars,
            tz_offset=timezone,
        )

        # Personality Traits
        self.personality_traits = SQLPersonalityTraits(db=self.db, max_traits=max_traits)

        # Mental State
        self.mental_states = SQLMentalStates(
            db=self.db, max_entities=max_mental_state_entities
        )

        # Drives
        self.drives = SQLDrives(
            db=self.db,
            default_decay_rate=default_decay_rate,
            max_history=max_history_drives,
            max_custom=max_custom_drives,
            tz_offset=timezone,
        )

    async def connect(self):
        await self.db.connect()
        if self.drives_enabled:
            await self.drives.bootstrap_fundamental_drives()  # Создает Фундаментальные мотивации, если их нет

    async def disconnect(self):
        await self.db.disconnect()

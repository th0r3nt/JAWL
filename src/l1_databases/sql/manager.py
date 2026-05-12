"""
Фасад для слоя реляционной памяти (SQL).

Инкапсулирует инициализацию БД и маршрутизирует вызовы к соответствующим
CRUD-контроллерам таблиц, передавая им лимиты из конфигурации (YAML).
"""

from pathlib import Path

from src.l1_databases.sql.db import SQLDB

# Таблицы
from src.l1_databases.sql.management.tasks.crud import SQLTasks
from src.l1_databases.sql.management.mental_states.crud import SQLMentalStates
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits
from src.l1_databases.sql.management.drives.crud import SQLDrives
from src.l1_databases.sql.management.notes import SQLNotes
from src.l1_databases.sql.management.hypotheses.crud import SQLHypotheses


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
        # Notes
        notes_max_notes: int = 5,
        # Ticks (Эпизодическая память)
        high_ticks: int = 3,
        medium_ticks: int = 7,
        low_ticks: int = 20,
        tick_action_max_chars: int = 2000,
        tick_result_max_chars: int = 5000,
        tick_thoughts_short_max_chars: int = 2000,
        tick_action_short_max_chars: int = 300,
        tick_result_short_max_chars: int = 300,
        # Mental State
        max_mental_state_entities: int = 10,
        # Drives
        drives_enabled: bool = True,
        dynamic_reduction: bool = True,
        pause_on_offline: bool = True,
        decay_rate: float = 5.0,
        decay_interval_sec: int = 3600,
        max_history_drives: int = 3,
        max_custom_drives: int = 5,
        fundamental_toggles: dict = None,
        # Hypotheses
        hypotheses_enabled: bool = True,
        max_hypotheses: int = 5,
        # Время
        timezone: int = 0,
    ) -> None:
        """
        Сборка всех компонентов SQL-памяти и передача лимитов из конфигурации.

        Все аргументы напрямую проксируются из `settings.yaml` для управления
        глубиной контекста и защитой от переполнения токенов LLM.
        """

        self.db = SQLDB(db_path=str(db_path))

        # Tasks
        self.tasks = SQLTasks(db=self.db, max_tasks=max_tasks)

        # Notes
        self.notes = SQLNotes(db=self.db, max_notes=notes_max_notes, tz_offset=timezone)

        # Ticks
        self.ticks = SQLTicks(
            db=self.db,
            high_ticks=high_ticks,
            medium_ticks=medium_ticks,
            low_ticks=low_ticks,
            action_max_chars=tick_action_max_chars,
            result_max_chars=tick_result_max_chars,
            thoughts_short_max_chars=tick_thoughts_short_max_chars,
            action_short_max_chars=tick_action_short_max_chars,
            result_short_max_chars=tick_result_short_max_chars,
            tz_offset=timezone,
        )

        # Personality Traits
        self.personality_traits = SQLPersonalityTraits(db=self.db, max_traits=max_traits)

        # Mental State
        self.mental_states = SQLMentalStates(
            db=self.db, max_entities=max_mental_state_entities
        )

        # Drives
        self.drives_enabled = drives_enabled
        self.drives = SQLDrives(
            db=self.db,
            decay_rate=decay_rate,
            dynamic_reduction=dynamic_reduction,
            pause_on_offline=pause_on_offline,
            decay_interval_sec=decay_interval_sec,
            max_history=max_history_drives,
            max_custom=max_custom_drives,
            tz_offset=timezone,
            fundamental_toggles=fundamental_toggles or {},
        )

        # Hypotheses
        self.hypotheses_enabled = hypotheses_enabled
        self.hypotheses = SQLHypotheses(
            db=self.db, max_hypotheses=max_hypotheses, tz_offset=timezone
        )

    async def connect(self) -> None:
        await self.db.connect()
        await self.tasks.bootstrap_migrations()
        await self.mental_states.bootstrap_migrations()

        if self.drives_enabled:
            await self.drives.bootstrap_fundamental_drives()
            await self.drives.adjust_downtime()

    async def disconnect(self) -> None:
        await self.db.disconnect()

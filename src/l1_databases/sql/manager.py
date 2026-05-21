"""
Facade for the relational memory layer (SQL).

Encapsulates DB initialization and routes calls to the corresponding
table CRUD controllers, passing them limits from the configuration (YAML).
"""

from pathlib import Path

from src.l1_databases.sql.db import SQLDB

# Tables
from src.l1_databases.sql.management.tasks.crud import SQLTasks
from src.l1_databases.sql.management.mental_states.crud import SQLMentalStates
from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits
from src.l1_databases.sql.management.drives.crud import SQLDrives
from src.l1_databases.sql.management.notes import SQLNotes
from src.l1_databases.sql.management.hypotheses.crud import SQLHypotheses


class SQLManager:
    """
    Facade for the SQL layer.
    Encapsulates connection to SQLite and assembly of CRUD handlers.
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
        # Ticks (Episodic Memory)
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
        max_history_drives: int = 4,
        max_custom_drives: int = 5,
        fundamental_config: dict = None,
        # Hypotheses
        hypotheses_enabled: bool = True,
        max_clusters_hypotheses: int = 3,
        max_hypotheses: int = 10,
        # Time
        timezone: int = 0,
    ) -> None:
        """
        Assembly of all SQL memory components and passing limits from the configuration.

        All arguments are directly proxied from `settings.yaml` to manage
        context depth and protect against LLM token overflow.
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
            dynamic_reduction=dynamic_reduction,
            pause_on_offline=pause_on_offline,
            max_history=max_history_drives,
            max_custom=max_custom_drives,
            tz_offset=timezone,
            fundamental_config=fundamental_config or {},
        )

        # Hypotheses
        self.hypotheses_enabled = hypotheses_enabled
        self.hypotheses = SQLHypotheses(
            db=self.db,
            max_clusters=max_clusters_hypotheses,
            max_hypotheses=max_hypotheses,
            tz_offset=timezone,
        )

    async def connect(self) -> None:
        """Opens connections, runs migrations, and initializes drives."""
        await self.db.connect()
        await self.tasks.bootstrap_migrations()
        await self.mental_states.bootstrap_migrations()
        await self.hypotheses.bootstrap_migrations()

        if self.drives_enabled:
            await self.drives.bootstrap_migrations()
            await self.drives.bootstrap_fundamental_drives()
            await self.drives.adjust_downtime()

    async def disconnect(self) -> None:
        """Safely closes connection."""
        await self.db.disconnect()

    # =================================================================================
    # ENCAPSULATION FOR HOT-RELOAD FROM META INTERFACE
    # =================================================================================

    def update_limits(self, module_name: str, new_limit: int) -> None:
        """
        Dynamically updates row limits for a specific CRUD controller.
        """

        if module_name == "tasks":
            self.tasks.max_tasks = new_limit

        elif module_name == "personality_traits":
            self.personality_traits.max_traits = new_limit

        elif module_name == "mental_states":
            self.mental_states.max_entities = new_limit

        elif module_name == "drives_custom":
            self.drives.max_custom = new_limit

    def update_context_depth(self, high: int, medium: int, low: int) -> None:
        """
        Dynamically updates episodic memory depth (Ticks).
        """

        self.ticks.high_ticks = high
        self.ticks.medium_ticks = medium
        self.ticks.low_ticks = low

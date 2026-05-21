"""
CRUD controller for managing internal needs (Drives) of the agent.

Implements a mathematical model of deficit growth from 0% to 100% over time.
Allows the agent to proactively perform tasks during moments of "boredom".
"""

import uuid
from typing import TYPE_CHECKING, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, desc, text

from src.utils.logger import main_logger
from src.utils.dtime import format_datetime
from src.utils._tools import get_last_active_time

from src.l1_databases.sql.tables import DriveTable, TickTable
from src.l1_databases.sql.management.drives.semantics import DRIVES_SEMANTIC_MATRIX

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB

from src.l3_agent.skills.registry import skill, SkillResult


class SQLDrives:
    """CRUD for managing internal needs (Drives) of the agent."""

    def __init__(
        self,
        db: "SQLDB",
        dynamic_reduction: bool = True,
        pause_on_offline: bool = True,
        max_history: int = 3,
        max_custom: int = 5,
        tz_offset: int = 0,
        fundamental_config: dict = None,
    ) -> None:
        """
        Initializes the motivator controller.

        Args:
            db: SQLite connection.
            max_history: Max history reflections count stored per drive.
            max_custom: Max custom drives count created by the agent.
            tz_offset: Timezone offset.
            fundamental_config: Configurations (rates and states) of fundamental drives.
        """

        self.db = db

        self.dynamic_reduction = dynamic_reduction
        self.pause_on_offline = pause_on_offline

        self.max_history = max_history
        self.max_custom = max_custom
        self.fundamental_config = fundamental_config or {}

        self.tz_offset = tz_offset

    async def bootstrap_migrations(self) -> None:
        """
        Soft migration to add decay_interval_sec column to older DBs.
        """

        async with self.db.engine.begin() as conn:
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE drives ADD COLUMN decay_interval_sec INTEGER DEFAULT 3600"
                    )
                )
                main_logger.info(
                    "[SQL DB] Successful migration of the Drives table (added decay_interval_sec)."
                )
            except Exception as e:
                main_logger.debug(
                    f"[SQL DB] Migration of the Drives table skipped (column probably already exists): {e}"
                )

    async def bootstrap_fundamental_drives(self) -> None:
        """
        Synchronizes fundamental (system-level) motivators with the DB based on YAML settings.
        If a drive is enabled but missing -> creates it. If disabled but exists -> deletes it.
        """

        fundamental_defs = {
            "curiosity": {
                "name": "Curiosity",
                "description": "The need to expand the information base. Initiates search for unknown concepts, analysis of external sources, and semantic memory enrichment.",
            },
            "social": {
                "name": "Social",
                "description": "The need for communication. Geared towards processing incoming requests, maintaining active status in communication channels, and proactively initiating dialogue.",
            },
            "mastery": {
                "name": "Mastery",
                "description": "Striving for efficiency and order. Requires progress on long-term tasks (TASKS), data structuring, and diagnostics.",
            },
        }

        async with self.db.session_factory() as session:
            for key, drive_def in fundamental_defs.items():
                drive_cfg = self.fundamental_config.get(key, {})
                is_enabled = drive_cfg.get("enabled", False)
                decay_cfg = drive_cfg.get("decay", {})
                rate = decay_cfg.get("rate", 10.0)
                interval = decay_cfg.get("interval_sec", 900)

                res = await session.execute(
                    select(DriveTable).where(DriveTable.name == drive_def["name"])
                )
                existing_drive = res.scalar_one_or_none()

                if is_enabled and not existing_drive:
                    # Drive is enabled, but missing -> create
                    new_drive = DriveTable(
                        id=str(uuid.uuid4())[:8],
                        name=drive_def["name"],
                        type="fundamental",
                        description=drive_def["description"],
                        decay_rate=rate,
                        decay_interval_sec=interval,
                        last_satisfied_at=datetime.now(timezone.utc),
                        recent_reflections=[],
                    )
                    session.add(new_drive)

                elif is_enabled and existing_drive:
                    # Dynamically update settings if the user changed them in YAML
                    existing_drive.decay_rate = rate
                    existing_drive.decay_interval_sec = interval

                elif not is_enabled and existing_drive:
                    # Drive is disabled, but exists in DB -> delete
                    await session.delete(existing_drive)

            await session.commit()

    @skill()
    async def satisfy_drive(
        self, drive_name: str, amount: int, reflection_summary: str
    ) -> SkillResult:
        """
        Reduces drive deficit.

        Recommended iterative satisfaction:
        1-9% (superficial),
        10-15% (meaningful),
        16-25% (major achievements).
        """

        amount = max(1, min(100, amount))

        async with self.db.session_factory() as session:
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

            drive = next((d for d in drives if d.name.lower() == drive_name.lower()), None)

            if not drive:
                return SkillResult.fail(f"Drive '{drive_name}' not found.")

            now = datetime.now(timezone.utc)
            last_sat = (
                drive.last_satisfied_at.replace(tzinfo=timezone.utc)
                if drive.last_satisfied_at.tzinfo is None
                else drive.last_satisfied_at
            )

            # Protection against legacy/corrupted data: decay_rate must be > 0, otherwise the mathematics
            # below falls apart: current_deficit will be negative or we get a ZeroDivisionError.
            if drive.decay_rate <= 0 or drive.decay_interval_sec <= 0:
                return SkillResult.fail(
                    f"Drive '{drive.name}' has invalid settings (rate={drive.decay_rate}, interval={drive.decay_interval_sec}). "
                    f"Positive numbers expected."
                )

            # Calculate current deficit via non-linear model
            current_deficit = self._calculate_deficit(
                last_sat, now, drive.decay_rate, drive.decay_interval_sec
            )

            # Calculate new deficit after satisfaction
            new_deficit = max(0.0, current_deficit - amount)

            # Calculate time when deficit would be equal to new_deficit
            intervals_ago = self._calculate_intervals_for_deficit(
                new_deficit, drive.decay_rate
            )
            drive.last_satisfied_at = now - timedelta(
                seconds=intervals_ago * drive.decay_interval_sec
            )

            time_str = format_datetime(now, self.tz_offset, "%m-%d %H:%M")
            entry = f"[{time_str}] Reduced by {amount}%: {reflection_summary}"

            current_refs = list(drive.recent_reflections)
            current_refs.insert(0, entry)
            drive.recent_reflections = current_refs[: self.max_history]

            await session.commit()

        main_logger.debug(f"[SQL DB] Deficit of drive '{drive.name}' reduced by {amount}%.")
        return SkillResult.ok("True")

    @skill()
    async def create_custom_drive(
        self,
        name: str,
        description: str,
        decay_rate: float = 10.0,
        decay_interval_sec: int = 900,
    ) -> SkillResult:
        """
        Creates custom drive/motivator.
        """

        # Validation
        if decay_rate <= 0 or decay_interval_sec <= 0:
            return SkillResult.fail(
                f"decay_rate and decay_interval_sec must be positive numbers. "
                f"Got: rate={decay_rate}, interval={decay_interval_sec}."
            )

        async with self.db.session_factory() as session:
            count_res = await session.execute(
                select(func.count(DriveTable.id)).where(DriveTable.type == "custom")
            )
            if count_res.scalar_one() >= self.max_custom:
                return SkillResult.fail(
                    f"Custom drives limit reached ({self.max_custom}). Delete old ones."
                )

            new_drive = DriveTable(
                id=str(uuid.uuid4())[:8],
                name=name,
                type="custom",
                description=description,
                decay_rate=decay_rate,
                decay_interval_sec=decay_interval_sec,
                last_satisfied_at=datetime.now(timezone.utc),
                recent_reflections=[],
            )
            session.add(new_drive)
            await session.commit()

        main_logger.debug(f"[SQL DB] Custom drive '{name}' created.")
        return SkillResult.ok("True")

    @skill()
    async def delete_custom_drive(self, drive_name: str) -> SkillResult:
        """
        Deletes custom drive.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

            drive = next((d for d in drives if d.name.lower() == drive_name.lower()), None)

            if not drive:
                return SkillResult.fail(f"Drive '{drive_name}' not found.")

            if drive.type == "fundamental":
                return SkillResult.fail("Access denied: Fundamental drives cannot be deleted.")

            await session.delete(drive)
            await session.commit()

        main_logger.debug(f"[SQL DB] Custom drive '{drive_name}' deleted.")
        return SkillResult.ok("True")

    def _get_drive_semantic_state(self, name: str, deficit: int, description: str) -> str:
        """
        Translates raw deficit percentages into utilitarian psychological states.
        Needed for the agent to see specific directives (Action Vector and Tone).
        """

        # Determine the step index (1-5) by 20% per step
        if deficit <= 20:
            step = 1
        elif deficit <= 40:
            step = 2
        elif deficit <= 60:
            step = 3
        elif deficit <= 80:
            step = 4
        else:
            step = 5

        # Choose text from the imported matrix
        if name in DRIVES_SEMANTIC_MATRIX:
            state_text = DRIVES_SEMANTIC_MATRIX[name][step].strip()
        else:
            # For custom drives, insert their description directly into the template
            template = DRIVES_SEMANTIC_MATRIX["Custom"][step].strip()
            state_text = template.format(description=description)

        return f"\n{state_text}"

    async def get_context_block(self, **kwargs: Any) -> str:
        """Generates a Markdown block with semantic self-perception for the system prompt."""

        async with self.db.session_factory() as session:
            result = await session.execute(select(DriveTable))
            drives = result.scalars().all()

        if not drives:
            return ""

        lines = [
            "## INTERNAL PSYCHOLOGICAL STATE",
            "Internal self-perceptions of the system, formed on the basis of a deficit of internal metrics:\n",
        ]

        now = datetime.now(timezone.utc)

        for d in drives:
            last_sat = (
                d.last_satisfied_at.replace(tzinfo=timezone.utc)
                if d.last_satisfied_at.tzinfo is None
                else d.last_satisfied_at
            )

            deficit = self._calculate_deficit(
                last_sat, now, d.decay_rate, d.decay_interval_sec
            )
            deficit_int = int(deficit)

            semantic_state = self._get_drive_semantic_state(d.name, deficit_int, d.description)

            # Output drive in format: * [CURIOSITY]: State text. (Deficit: X%)
            lines.append(f"* [{d.name}; Deficit: {deficit_int}%]: \n{semantic_state}")

            # Keep reflections history so the LLM understands what it did recently to close this need
            if d.recent_reflections:
                lines.append("  * Recent deficit reductions:*")
                for ref in d.recent_reflections[
                    :2
                ]:  # Take only the 2 latest to avoid bloating
                    limit = 200
                    short_ref = ref if len(ref) <= limit else ref[:limit] + "... [Truncated]"
                    lines.append(f"    - {short_ref}")
            lines.append("")  # Empty line

        return "\n".join(lines).strip()

    # =======================================================================================
    # SERVICE METHODS
    # =======================================================================================

    def _calculate_deficit(
        self, last_sat: datetime, now: datetime, decay_rate: float, decay_interval_sec: int
    ) -> float:
        """
        Direct math: calculates current deficit percentage from elapsed time.
        """

        # Calculate time (in intervals) to complete each step
        intervals = (now - last_sat).total_seconds() / max(1, decay_interval_sec)

        if not self.dynamic_reduction:
            return min(100.0, intervals * decay_rate)

        # Calculate time (in intervals) to complete each step
        t50 = 50.0 / decay_rate
        t80 = t50 + 30.0 / (decay_rate * 0.5)

        if intervals <= t50:
            deficit = intervals * decay_rate
        elif intervals <= t80:
            deficit = 50.0 + (intervals - t50) * (decay_rate * 0.5)
        else:
            deficit = 80.0 + (intervals - t80) * (decay_rate * 0.2)

        return min(100.0, deficit)

    def _calculate_intervals_for_deficit(self, deficit: float, decay_rate: float) -> float:
        """
        Inverse math: translates deficit percentage back to spent intervals.
        """

        if not self.dynamic_reduction:
            return deficit / decay_rate

        t50 = 50.0 / decay_rate
        t80 = t50 + 30.0 / (decay_rate * 0.5)

        if deficit <= 50.0:
            return deficit / decay_rate
        elif deficit <= 80.0:
            return t50 + (deficit - 50.0) / (decay_rate * 0.5)
        else:
            return t80 + (deficit - 80.0) / (decay_rate * 0.2)

    async def adjust_downtime(self) -> None:
        """
        Compensates for the time the agent was shut down (downtime),
        shifting last_satisfied_at for all drives.
        This prevents an instant jump in deficit after long offline periods.
        """

        if not self.pause_on_offline:
            return

        last_active = get_last_active_time()
        last_tick_time = None

        if last_active:
            last_tick_time = datetime.fromtimestamp(last_active, tz=timezone.utc)
        else:
            async with self.db.session_factory() as session:
                res = await session.execute(
                    select(TickTable.created_at).order_by(desc(TickTable.created_at)).limit(1)
                )
                db_tick = res.scalar_one_or_none()
                if db_tick:
                    last_tick_time = (
                        db_tick.replace(tzinfo=timezone.utc)
                        if db_tick.tzinfo is None
                        else db_tick
                    )

        if not last_tick_time:
            return

        now = datetime.now(timezone.utc)
        downtime = now - last_tick_time

        if downtime.total_seconds() > 60:
            async with self.db.session_factory() as session:
                drives_res = await session.execute(select(DriveTable))
                drives = drives_res.scalars().all()

                adjusted = 0
                for d in drives:
                    sat_time = (
                        d.last_satisfied_at.replace(tzinfo=timezone.utc)
                        if d.last_satisfied_at.tzinfo is None
                        else d.last_satisfied_at
                    )

                    # Игнорируем драйвы, которые были изменены строго после выключения системы
                    if sat_time > last_tick_time:
                        continue

                    d.last_satisfied_at = sat_time + downtime
                    adjusted += 1

                if adjusted > 0:
                    await session.commit()
                    main_logger.info(
                        f"[SQL DB] Downtime ({int(downtime.total_seconds())} sec) compensated for {adjusted} motivators."
                    )

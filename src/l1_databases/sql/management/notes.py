"""
CRUD controller for the Notes table (Working Notes).

Provides the agent with working memory ("stickers on the monitor").
These notes always stay in the system prompt, which helps avoid losing
important intermediate data between distant ReAct loops.
"""

import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import select, delete, func

from src.utils.logger import main_logger
from src.utils.dtime import format_datetime
from src.utils._tools import truncate_text

from src.l1_databases.sql.tables import NoteTable

from src.l3_agent.skills.registry import skill, SkillResult

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLNotes:
    """Operational notes controller (Working Memory)."""

    def __init__(self, db: "SQLDB", max_notes: int = 5, tz_offset: int = 0) -> None:
        """
        Initializes the notes controller.

        Args:
            db: Connection to SQLite.
            max_notes: Maximum number of active notes.
            tz_offset: Timezone offset.
        """

        self.db = db
        self.max_notes = max_notes
        self.tz_offset = tz_offset

    @skill()
    async def add_note(self, content: str) -> SkillResult:
        """
        Creates note. Stays permanently in system context.
        """

        if not content or not content.strip():
            return SkillResult.fail("Error: Note text cannot be empty.")

        note_id = str(uuid.uuid4())[:8]

        async with self.db.session_factory() as session:
            count_res = await session.execute(select(func.count(NoteTable.id)))
            if count_res.scalar_one() >= self.max_notes:
                return SkillResult.fail(
                    f"Notes limit reached ({self.max_notes}). It is recommended to delete old ones before creating a new one."
                )

            new_note = NoteTable(id=note_id, content=content.strip())
            session.add(new_note)
            await session.commit()

        msg = f"Note successfully created (ID: {note_id})."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(f"True. ID: {note_id}")

    @skill()
    async def update_note(self, note_id: str, content: str) -> SkillResult:
        """
        Fully overwrites note text.
        """
        if not content or not content.strip():
            return SkillResult.fail("Error: Note text cannot be empty.")

        async with self.db.session_factory() as session:
            result = await session.execute(select(NoteTable).where(NoteTable.id == note_id))
            note = result.scalar_one_or_none()

            if not note:
                return SkillResult.fail(f"Note with ID '{note_id}' not found.")

            note.content = content.strip()
            # updated_at will automatically update via onupdate in table definition
            await session.commit()

        msg = f"Note '{note_id}' successfully updated."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    @skill()
    async def delete_note(self, note_id: str) -> SkillResult:
        """
        Deletes note.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(delete(NoteTable).where(NoteTable.id == note_id))
            await session.commit()

            if result.rowcount == 0:
                return SkillResult.fail(f"Note with ID '{note_id}' not found.")

        msg = f"Note '{note_id}' deleted."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    @skill()
    async def list_all_notes(self) -> SkillResult:
        """
        Reads full content of all current notes.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(
                select(NoteTable).order_by(NoteTable.updated_at.desc())
            )
            notes = result.scalars().all()

        if not notes:
            return SkillResult.ok("Notes list is empty.")

        lines = ["Notes:"]
        for note in notes:
            time_str = format_datetime(note.updated_at, self.tz_offset, "%Y-%m-%d %H:%M")
            lines.append(f"\n--- [ID: {note.id}] (Updated: {time_str}) ---")
            lines.append(note.content)

        return SkillResult.ok("\n".join(lines))

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Returns a formatted context block for the system prompt.
        Long notes are truncated to avoid burning the token window.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(
                select(NoteTable).order_by(NoteTable.updated_at.desc())
            )
            notes = result.scalars().all()

        if not notes:
            return ""

        lines = [f"NOTES (Max: {self.max_notes})"]
        for note in notes:
            time_str = format_datetime(note.updated_at, self.tz_offset, "%m-%d %H:%M")
            content = note.content.replace("\n", " ")
            content = truncate_text(content, max_chars=500, suffix="...[Truncated]")
            lines.append(f"[{note.id}] ({time_str}): {content}")

        return "\n".join(lines).strip()

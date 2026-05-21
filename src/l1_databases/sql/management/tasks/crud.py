"""
CRUD controller for long-term tasks (Tasks).
Uses the Eisenhower Matrix for priority distribution.
"""

import uuid
import ast
from datetime import datetime
from typing import Optional, TYPE_CHECKING, Any, Literal
from sqlalchemy import select, delete, func, text

from src.utils.logger import main_logger
from src.utils.dtime import get_timezone

from src.l1_databases.sql.tables import TaskTable
from src.l1_databases.sql.management.tasks.semantics import (
    build_eisenhower_matrix,
    ALLOWED_TAGS,
    STATUS_EMOJIS,
)

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB

from src.l3_agent.skills.registry import skill, SkillResult


class SQLTasks:
    """CRUD for managing agent's long-term tasks (Eisenhower Matrix)."""

    def __init__(self, db: "SQLDB", max_tasks: int = 15, tz_offset: int = 0) -> None:
        self.db = db
        self.max_tasks = max_tasks
        self.tz_offset = tz_offset

    async def bootstrap_migrations(self) -> None:
        """
        Soft migration to add quadrant column to older databases.
        """

        async with self.db.engine.begin() as conn:
            try:
                await conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN quadrant INTEGER DEFAULT 2")
                )
                main_logger.info(
                    "[SQL DB] Successful migration of the Tasks table (added quadrant)."
                )
            except Exception as e:
                main_logger.debug(
                    f"[SQL DB] Migration of the Tasks table skipped (column probably already exists): {e}"
                )

    def _validate_tags(self, tags: Any) -> tuple[bool, str, list[str]]:
        """
        Protective tag parser against LLM hallucinations.
        """

        if not tags:
            return True, "", []

        if isinstance(tags, str):
            tags = tags.strip()
            if tags.startswith("[") and tags.endswith("]"):
                try:
                    tags = ast.literal_eval(tags)
                except Exception:
                    tags = [t.strip().strip("'\"") for t in tags[1:-1].split(",")]
            else:
                tags = [tags]

        if not isinstance(tags, list):
            return False, "Error: Tags must be an array (list) of strings.", []

        clean_tags = [str(t).strip() for t in tags if str(t).strip()]
        for tag in clean_tags:
            if tag not in ALLOWED_TAGS:
                return (
                    False,
                    f"Tag '{tag}' is invalid. Allowed tags: {', '.join(ALLOWED_TAGS)}",
                    [],
                )
        return True, "", clean_tags

    @skill()
    async def create_task(
        self,
        title: str,
        description: str,
        quadrant: Literal[1, 2, 3, 4],
        tags: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        subtasks: Optional[list[dict[str, Any]]] = None,
        due_date_str: Optional[str] = None,
    ) -> SkillResult:
        """
        Creates long-term Eisenhower matrix task.

        dependencies: Blocking task IDs.
        subtasks: Progress tracking checklist.
        due_date_str: 'YYYY-MM-DD HH:MM' deadline.
        """

        if quadrant not in [1, 2, 3, 4]:
            return SkillResult.fail("Error: quadrant must be a number from 1 to 4.")

        task_id = str(uuid.uuid4())[:8]
        if tags is None:
            tags = []

        is_valid, err_msg, clean_tags = self._validate_tags(tags)
        if not is_valid:
            return SkillResult.fail(err_msg)

        due_date_ts = None
        if due_date_str:
            try:
                tz = get_timezone(self.tz_offset)
                dt = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                due_date_ts = dt.timestamp()
            except ValueError:
                return SkillResult.fail(
                    "Error: Invalid due_date_str format. Must use 'YYYY-MM-DD HH:MM'."
                )

        async with self.db.session_factory() as session:
            count_res = await session.execute(select(func.count(TaskTable.id)))
            if count_res.scalar_one() >= self.max_tasks:
                return SkillResult.fail(
                    f"Tasks limit reached ({self.max_tasks}). It is necessary to complete or delete old tasks."
                )

            new_task = TaskTable(
                id=task_id,
                title=title,
                description=description,
                status="todo",
                progress=0,
                quadrant=quadrant,
                tags=clean_tags,
                dependencies=dependencies or [],
                subtasks=subtasks or [],
                due_date=due_date_ts,
                context=None,
            )
            session.add(new_task)
            await session.commit()

        msg = f"Task '{title}' created (Quadrant {quadrant}). ID: {task_id}"
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(f"True. ID: {task_id}")

    @skill()
    async def move_task_to_quadrant(
        self, task_id: str, new_quadrant: Literal[1, 2, 3, 4]
    ) -> SkillResult:
        """
        Moves task to new Eisenhower quadrant.
        """

        if new_quadrant not in [1, 2, 3, 4]:
            return SkillResult.fail("Error: quadrant must be a number from 1 to 4.")

        async with self.db.session_factory() as session:
            result = await session.execute(select(TaskTable).where(TaskTable.id == task_id))
            task = result.scalar_one_or_none()

            if not task:
                return SkillResult.fail(f"Task with ID {task_id} not found.")

            old_quadrant = task.quadrant
            task.quadrant = new_quadrant
            await session.commit()

        msg = f"Task {task_id} moved from Quadrant {old_quadrant} to Quadrant {new_quadrant}."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    @skill()
    async def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[
            Literal["todo", "in_progress", "blocked", "done", "cancelled"]
        ] = None,
        progress: Optional[int] = None,
        tags: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        subtasks: Optional[list[dict[str, Any]]] = None,
        context: Optional[str] = None,
    ) -> SkillResult:
        """
        Updates existing task parameters.
        """

        if status and status not in STATUS_EMOJIS.keys():
            return SkillResult.fail(
                f"Invalid status. Allowed: {', '.join(STATUS_EMOJIS.keys())}"
            )

        clean_tags = None
        if tags is not None:
            is_valid, err_msg, clean_tags = self._validate_tags(tags)
            if not is_valid:
                return SkillResult.fail(err_msg)

        async with self.db.session_factory() as session:
            result = await session.execute(select(TaskTable).where(TaskTable.id == task_id))
            task = result.scalar_one_or_none()

            if not task:
                return SkillResult.fail(f"Task with ID {task_id} not found.")

            if title is not None:
                task.title = title
            if description is not None:
                task.description = description
            if status is not None:
                task.status = status
                if status == "done":
                    task.progress = 100
            if progress is not None:
                task.progress = max(0, min(100, progress))
                if task.progress == 100 and task.status != "done":
                    task.status = "done"
            if clean_tags is not None:
                task.tags = clean_tags
            if dependencies is not None:
                task.dependencies = dependencies
            if subtasks is not None:
                task.subtasks = subtasks
            if context is not None:
                task.context = context

            await session.commit()

        msg = f"Task {task_id} successfully updated."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    @skill()
    async def delete_task(self, task_id: str) -> SkillResult:
        """
        Deletes task from DB.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(delete(TaskTable).where(TaskTable.id == task_id))
            await session.commit()
            if result.rowcount == 0:
                return SkillResult.fail(f"Task with ID {task_id} not found.")

        msg = f"Task {task_id} deleted."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Formats the active tasks block for the system prompt using the Eisenhower Matrix.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(select(TaskTable))
            tasks = result.scalars().all()

        return build_eisenhower_matrix(tasks, self.max_tasks, self.tz_offset)

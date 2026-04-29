import uuid
import ast
from datetime import datetime
from typing import Optional, TYPE_CHECKING, Any, Literal
from sqlalchemy import select, delete, func

from src.l3_agent.skills.registry import skill, SkillResult
from src.utils.logger import system_logger
from src.utils.dtime import get_timezone, format_timestamp
from src.l1_databases.sql.tables import TaskTable

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB

ALLOWED_TAGS = [
    "priority:critical",
    "priority:high",
    "priority:low",
    "domain:research",
    "domain:code",
    "domain:os",
    "domain:social",
    "type:feature",
    "type:bugfix",
    "type:routine",
    "type:learning",
]

STATUS_EMOJIS = {
    "todo": "TODO",
    "in_progress": "IN_PROGRESS",
    "blocked": "BLOCKED",
    "done": "DONE",
    "cancelled": "CANCELLED",
}


class SQLTasks:
    """CRUD для управления долгосрочными задачами агента (Tasks v2)."""

    def __init__(self, db: "SQLDB", max_tasks: int = 15, tz_offset: int = 0):
        self.db = db
        self.max_tasks = max_tasks
        self.tz_offset = tz_offset

    def _validate_tags(self, tags: Any) -> tuple[bool, str, list[str]]:
        """Броня для тегов: конвертирует строку в список и фильтрует мусор."""
        if not tags:
            return True, "", []

        # Защита от галлюцинаций LLM (когда она присылает строку "[tag1, tag2]")
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
            return False, "Ошибка: Теги должны быть массивом (списком) строк.", []

        clean_tags = [str(t).strip() for t in tags if str(t).strip()]
        for tag in clean_tags:
            if tag not in ALLOWED_TAGS:
                return (
                    False,
                    f"Тег '{tag}' недопустим. Разрешенные теги: {', '.join(ALLOWED_TAGS)}",
                    [],
                )
        return True, "", clean_tags

    @skill()
    async def create_task(
        self,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        subtasks: Optional[list[dict[str, Any]]] = None,
        due_date_str: Optional[str] = None,
    ) -> SkillResult:
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
                    "Ошибка: Неверный формат due_date_str. Необходимо использовать 'YYYY-MM-DD HH:MM'."
                )

        safe_subtasks = subtasks or []
        safe_deps = dependencies or []

        async with self.db.session_factory() as session:
            count_res = await session.execute(select(func.count(TaskTable.id)))
            if count_res.scalar_one() >= self.max_tasks:
                return SkillResult.fail(
                    f"Достигнут лимит задач ({self.max_tasks}). Необходимо завершить или удалить старые задачи."
                )

            new_task = TaskTable(
                id=task_id,
                title=title,
                description=description,
                status="todo",
                progress=0,
                tags=clean_tags,
                dependencies=safe_deps,
                subtasks=safe_subtasks,
                due_date=due_date_ts,
                context=None,
            )
            session.add(new_task)
            await session.commit()

        msg = f"Задача '{title}' создана. ID: {task_id}"
        system_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

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
        due_date_str: Optional[str] = None,
        context: Optional[str] = None,
    ) -> SkillResult:
        if status and status not in STATUS_EMOJIS.keys():
            return SkillResult.fail(
                f"Недопустимый статус. Варианты: {', '.join(STATUS_EMOJIS.keys())}"
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
                return SkillResult.fail(f"Задача с ID {task_id} не найдена.")

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

            if due_date_str is not None:
                try:
                    tz = get_timezone(self.tz_offset)
                    dt = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                    task.due_date = dt.timestamp()

                except ValueError:
                    return SkillResult.fail("Ошибка: Неверный формат due_date_str.")

            await session.commit()

        msg = f"Задача {task_id} успешно обновлена."
        system_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    @skill()
    async def delete_task(self, task_id: str) -> SkillResult:
        async with self.db.session_factory() as session:
            result = await session.execute(delete(TaskTable).where(TaskTable.id == task_id))
            await session.commit()
            if result.rowcount == 0:
                return SkillResult.fail(f"Задача с ID {task_id} не найдена.")

        msg = f"Задача {task_id} удалена."
        system_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    async def get_context_block(self, **kwargs) -> str:
        async with self.db.session_factory() as session:
            result = await session.execute(select(TaskTable))
            tasks = result.scalars().all()

        if not tasks:
            return f"## TASKS\nMax tasks allowed: {self.max_tasks}\nAllowed tags: {', '.join(ALLOWED_TAGS)}\n\nСписок задач пуст."

        task_statuses = {t.id: t.status for t in tasks}
        lines = [
            "## TASKS",
            f"Max tasks allowed: {self.max_tasks}",
            f"Allowed tags: {', '.join(ALLOWED_TAGS)}",
            "",
        ]

        for t in tasks:
            status_icon = STATUS_EMOJIS.get(t.status, t.status.upper())
            lines.append(f"[Task ID: `{t.id}`] {status_icon} | Progress: {t.progress}%")
            lines.append(f"* Title: {t.title}")
            lines.append(f"* Description: {t.description}")

            tags_str = f"[{', '.join(t.tags)}]" if t.tags else "None"
            lines.append(f"* Tags: {tags_str}")
            deadline = (
                format_timestamp(t.due_date, self.tz_offset, "%Y-%m-%d %H:%M")
                if t.due_date
                else "None"
            )
            lines.append(f"* Deadline: {deadline}")

            if not t.dependencies:
                lines.append("* Dependencies: None")

            else:
                deps_info = []

                for dep_id in t.dependencies:
                    d_stat = task_statuses.get(dep_id, "unknown")
                    if d_stat not in ("done", "cancelled", "unknown"):
                        deps_info.append(f"`{dep_id}` (⛔ Блокирует)")
                    else:
                        deps_info.append(f"`{dep_id}` (✓ {d_stat})")

                lines.append(f"* Dependencies: {', '.join(deps_info)}")

            if not t.subtasks:
                lines.append("* Subtasks: None")

            else:
                lines.append("* Subtasks:")

                for sub in t.subtasks:
                    mark = "x" if sub.get("is_done") else " "
                    lines.append(f"  [{mark}] {sub.get('title', 'unknown')}")

            lines.append(f"* Context: {t.context if t.context else 'Пусто'}")
            lines.append("")

        return "\n".join(lines).strip()

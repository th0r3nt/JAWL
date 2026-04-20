import uuid
from typing import Optional, TYPE_CHECKING
from sqlalchemy import select, delete, func

from src.l3_agent.skills.registry import skill, SkillResult
from src.utils.logger import system_logger
from src.l1_databases.sql.tables import TaskTable

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLTasks:
    """CRUD для управления долгосрочными задачами агента."""

    def __init__(self, db: "SQLDB", max_tasks: int = 15):
        self.db = db
        self.max_tasks = max_tasks

    @skill()
    async def create_task(
        self, description: str, term: Optional[str] = None, context: Optional[str] = None
    ) -> SkillResult:
        """Создает новую долгосрочную задачу в базе данных."""
        task_id = str(uuid.uuid4())[:8]

        async with self.db.session_factory() as session:
            # Проверка лимита
            count_res = await session.execute(select(func.count(TaskTable.id)))
            if count_res.scalar_one() >= self.max_tasks:
                return SkillResult.fail(
                    f"Достигнут лимит задач ({self.max_tasks}). Рекомендуется завершить или удалить старые задачи перед созданием новых."
                )

            new_task = TaskTable(
                id=task_id, description=description, term=term, context=context
            )
            session.add(new_task)
            await session.commit()

        msg = f"Задача создана. ID: {task_id}"
        system_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    async def get_tasks(self) -> SkillResult:
        """Возвращает список всех текущих задач."""
        async with self.db.session_factory() as session:
            result = await session.execute(select(TaskTable))
            tasks = result.scalars().all()

        if not tasks:
            return SkillResult.ok("Список задач пуст.")

        lines = []
        for t in tasks:
            term_str = f" | Срок: {t.term}" if t.term else ""
            ctx_str = f" | Контекст: {t.context}" if t.context else ""
            lines.append(f"- [ID: `{t.id}`] {t.description}{term_str}{ctx_str}")

        return SkillResult.ok("\n".join(lines))

    @skill()
    async def update_task(
        self,
        task_id: str,
        description: Optional[str] = None,
        term: Optional[str] = None,
        context: Optional[str] = None,
    ) -> SkillResult:
        """Обновляет задачу по ID (передавать только те поля, которые нужно изменить)."""
        async with self.db.session_factory() as session:
            result = await session.execute(select(TaskTable).where(TaskTable.id == task_id))
            task = result.scalar_one_or_none()

            if not task:
                return SkillResult.fail(f"Задача с ID {task_id} не найдена.")

            if description is not None:
                task.description = description
            if term is not None:
                task.term = term
            if context is not None:
                task.context = context

            await session.commit()

        msg = f"Задача {task_id} обновлена."
        system_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    @skill()
    async def delete_task(self, task_id: str) -> SkillResult:
        """Удаляет задачу по ID (отмечает как выполненную)."""
        async with self.db.session_factory() as session:
            result = await session.execute(delete(TaskTable).where(TaskTable.id == task_id))
            await session.commit()

            if result.rowcount == 0:  # type: ignore[attr-defined]
                return SkillResult.fail(f"Задача с ID {task_id} не найдена.")

        msg = f"Задача {task_id} удалена."
        system_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок для контекста агента.
        """

        res = await self.get_tasks()
        return f"## TASKS\n{res.message}"

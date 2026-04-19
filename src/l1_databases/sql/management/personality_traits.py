import uuid
from typing import Optional, TYPE_CHECKING
from sqlalchemy import select, delete

from src.l3_agent.skills.registry import skill, SkillResult
from src.utils.logger import system_logger
from src.l1_databases.sql.tables import PersonalityTraitTable

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLPersonalityTraits:
    """CRUD для управления приобретенными чертами характера агента."""

    def __init__(self, db: "SQLDB"):
        self.db = db

    @skill()
    async def add_trait(
        self, name: str, description: str, reason: Optional[str] = None, context: Optional[str] = None
    ) -> SkillResult:
        """Добавляет новую приобретенную черту личности."""

        trait_id = str(uuid.uuid4())[:8]

        async with self.db.session_factory() as session:
            new_trait = PersonalityTraitTable(
                id=trait_id, name=name, description=description, reason=reason, context=context
            )
            session.add(new_trait)
            await session.commit()

        msg = f"Черта личности '{name}' успешно добавлена. ID: {trait_id}"
        system_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    async def get_traits(self) -> SkillResult:
        """Возвращает список всех текущих приобретенных черт личности."""

        async with self.db.session_factory() as session:
            result = await session.execute(select(PersonalityTraitTable))
            traits = result.scalars().all()

        if not traits:
            return SkillResult.ok("Список приобретенных черт личности пуст.")

        lines = []
        for t in traits:
            reason_str = f" | Причина: {t.reason}" if t.reason else ""
            ctx_str = f" | Контекст: {t.context}" if t.context else ""
            lines.append(
                f"- [ID: `{t.id}`] '{t.name}': {t.description}{reason_str}{ctx_str}"
            )

        return SkillResult.ok("\n".join(lines))

    @skill()
    async def remove_trait(self, trait_id: str) -> SkillResult:
        """Удаляет черту личности по ID, если она больше не актуальна."""
        async with self.db.session_factory() as session:
            result = await session.execute(delete(PersonalityTraitTable).where(PersonalityTraitTable.id == trait_id))
            await session.commit()

            if result.rowcount == 0:
                return SkillResult.fail(f"Черта личности с ID {trait_id} не найдена.")

        msg = f"Черта личности {trait_id} удалена."
        system_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок для контекста агента.
        """
        res = await self.get_traits()
        return f"## PERSONALITY TRAITS\n{res.message}"
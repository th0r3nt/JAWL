import uuid
from typing import Optional, TYPE_CHECKING, Literal, Any, Dict
from sqlalchemy import select, delete, func, text

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents
from src.l3_agent.subconscious.schema import Pattern

from src.l1_databases.sql.tables import MentalStateTable
from src.l1_databases.sql.management.mental_states.semantics import build_mental_states

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLMentalStates:
    def __init__(self, db: "SQLDB", max_entities: int = 10) -> None:
        self.db = db
        self.max_entities = max_entities

    async def bootstrap_migrations(self) -> None:
        """
        Мягкая миграция для добавления новых колонок CRM в старые базы данных.
        """

        async with self.db.engine.begin() as conn:
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE mental_states ADD COLUMN attitude TEXT DEFAULT 'Neutral'"
                    )
                )
                await conn.execute(
                    text("ALTER TABLE mental_states ADD COLUMN directives TEXT DEFAULT ''")
                )
                await conn.execute(
                    text("ALTER TABLE mental_states ADD COLUMN relations JSON DEFAULT '{}'")
                )
                await conn.execute(
                    text(
                        "ALTER TABLE mental_states ADD COLUMN epistemic_state TEXT DEFAULT ''"
                    )
                )
                main_logger.info(
                    "[SQL DB] Выполнена успешная миграция таблицы MentalStates (добавлены CRM колонки)."
                )
            except Exception as e:
                main_logger.debug(
                    f"[SQL DB] Миграция таблицы Tasks пропущена (возможно, колонка уже существует): {e}"
                )

    @skill(swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.REFLECTION])
    async def create_mental_state(
        self,
        name: str,
        tier: Literal["high", "medium", "low", "background"],
        category: Literal["subject", "object"],
        description: str,
        status: str,
        attitude: str = "Neutral",
        directives: str = "",
        epistemic_state: str = "",
        relations: Optional[Dict[str, str]] = None,
        context: Optional[str] = None,
        related_information: Optional[str] = None,
    ) -> SkillResult:
        """
        Registers new subject/object in Mental States CRM. 
        
        attitude: Subjective stance.
        directives: Individual interaction guidelines.
        epistemic_state: Theory of Mind (what the subject knows).
        relations: Dict of links {"Entity_ID": "Relation description"}.
        """

        if tier not in ("high", "medium", "low", "background"):
            return SkillResult.fail(
                "Ошибка: tier должен быть 'high', 'medium', 'low' или 'background'."
            )
        if category not in ("subject", "object"):
            return SkillResult.fail("Ошибка: category должен быть 'subject' или 'object'.")

        async with self.db.session_factory() as session:
            count_res = await session.execute(select(func.count(MentalStateTable.id)))
            if count_res.scalar_one() >= self.max_entities:
                return SkillResult.fail(
                    f"Достигнут лимит сущностей ({self.max_entities}). Удалите неактуальные."
                )

            state_id = str(uuid.uuid4())[:8]
            new_state = MentalStateTable(
                id=state_id,
                name=name,
                tier=tier,
                category=category,
                description=description,
                status=status,
                attitude=attitude,
                directives=directives,
                epistemic_state=epistemic_state,
                relations=relations or {},
                context=context,
                related_information=related_information,
            )
            session.add(new_state)
            await session.commit()

        msg = f"Сущность '{name}' добавлена в Active CRM. ID: {state_id}"
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok(f"True. ID: {state_id}")

    @skill(swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.REFLECTION])
    async def get_mental_states(self) -> SkillResult:
        """
        Returns list of all tracked entities, their attitudes, and relations.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(select(MentalStateTable))
            states = result.scalars().all()

        return SkillResult.ok(build_mental_states(states, self.max_entities))

    @skill(swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.REFLECTION])
    async def update_mental_state(
        self,
        state_id: str,
        tier: Optional[Literal["high", "medium", "low", "background"]] = None,
        category: Optional[Literal["subject", "object"]] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        attitude: Optional[str] = None,
        directives: Optional[str] = None,
        epistemic_state: Optional[str] = None,
        relations: Optional[Dict[str, str]] = None,
        context: Optional[str] = None,
        related_information: Optional[str] = None,
    ) -> SkillResult:
        """
        Updates specific fields of tracked entity.
        """

        if tier and tier not in ("high", "medium", "low", "background"):
            return SkillResult.fail(
                "Ошибка: tier должен быть 'high', 'medium', 'low' или 'background'."
            )
        if category and category not in ("subject", "object"):
            return SkillResult.fail("Ошибка: category должен быть 'subject' или 'object'.")

        async with self.db.session_factory() as session:
            result = await session.execute(
                select(MentalStateTable).where(MentalStateTable.id == state_id)
            )
            state = result.scalar_one_or_none()

            if not state:
                return SkillResult.fail(f"MentalState с ID {state_id} не найден.")

            if tier:
                state.tier = tier
            if category:
                state.category = category
            if description is not None:
                state.description = description
            if status is not None:
                state.status = status
            if attitude is not None:
                state.attitude = attitude
            if directives is not None:
                state.directives = directives
            if epistemic_state is not None:
                state.epistemic_state = epistemic_state
            if relations is not None:
                state.relations = relations
            if context is not None:
                state.context = context
            if related_information is not None:
                state.related_information = related_information

            await session.commit()

        msg = f"Сущность '{state.name}' (ID: {state_id}) обновлена."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    @skill(swarm=[Subagents.ARCHIVIST], subconscious=[Pattern.FORGETTING])
    async def delete_mental_state(self, state_id: str) -> SkillResult:
        """
        Deletes entity from database.
        """

        async with self.db.session_factory() as session:
            result = await session.execute(
                delete(MentalStateTable).where(MentalStateTable.id == state_id)
            )
            await session.commit()
            if result.rowcount == 0:
                return SkillResult.fail(f"Сущность с ID {state_id} не найдена.")

        msg = f"Сущность с ID {state_id} удалена из радара."
        main_logger.debug(f"[SQL DB] {msg}")
        return SkillResult.ok("True")

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Провайдер контекста для ContextRegistry.
        """

        res = await self.get_mental_states()
        return res.message

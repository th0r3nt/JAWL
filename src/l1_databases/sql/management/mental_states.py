import uuid
from typing import Optional, TYPE_CHECKING, Literal
from datetime import datetime, timezone
from sqlalchemy import select, delete, func

from src.l3_agent.skills.registry import skill, SkillResult
from src.utils.logger import system_logger
from src.l1_databases.sql.tables import MentalStateTable

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLMentalStates:
    """CRUD для управления таблицей MentalState (состояния сущностей)."""

    def __init__(self, db: "SQLDB", max_entities: int = 10):
        self.db = db
        self.max_entities = max_entities

    @skill()
    async def create_mental_state(
        self,
        name: str,
        tier: Literal["high", "medium", "low", "background"],
        category: Literal["subject", "object"],
        description: str,
        status: str,
        context: Optional[str] = None,
        related_information: Optional[str] = None,
    ) -> SkillResult:
        """
        Создает новую запись в MentalState (отслеживание сущности).
        related_information: связанная информация, например, аккаунты субъекта в разных соц. сетях и подобное.
        """

        if tier not in ("high", "medium", "low", "background"):
            return SkillResult.fail(
                "Ошибка: tier должен быть 'high', 'medium', 'low' или 'background'."
            )
        if category not in ("subject", "object"):
            return SkillResult.fail("Ошибка: category должен быть 'subject' или 'object'.")

        async with self.db.session_factory() as session:
            # Проверка лимита
            count_res = await session.execute(select(func.count(MentalStateTable.id)))
            if count_res.scalar_one() >= self.max_entities:
                return SkillResult.fail(
                    f"Достигнут лимит макс. хранимых MentalState сущностей ({self.max_entities}). Рекомендуется удалить неактуальные."
                )

            state_id = str(uuid.uuid4())[:8]
            new_state = MentalStateTable(
                id=state_id,
                name=name,
                tier=tier,
                category=category,
                description=description,
                status=status,
                context=context,
                related_information=related_information,
            )
            session.add(new_state)
            await session.commit()

        msg = f"MentalState для '{name}' успешно создан. ID: {state_id}"
        system_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    async def get_mental_states(self) -> SkillResult:
        """Возвращает список всех текущих отслеживаемых сущностей (MentalState)."""

        async with self.db.session_factory() as session:
            result = await session.execute(select(MentalStateTable))
            states = result.scalars().all()

        if not states:
            return SkillResult.ok("Список MentalState пуст.")

        lines = []
        for s in states:
            # Высчитываем время с последнего обновления
            updated_at_aware = s.updated_at.replace(tzinfo=timezone.utc) if s.updated_at.tzinfo is None else s.updated_at
            delta = datetime.now(timezone.utc) - updated_at_aware
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            time_ago = f"{hours}h {minutes}m ago"

            # Форматируем красивый вывод
            lines.append(
                f"[{s.name}] (id: `{s.id}` | tier: {s.tier} | category: {s.category} | updated at: {time_ago})"
            )
            lines.append(f"* description: {s.description}")
            lines.append(f"* status: {s.status}")

            if s.context:
                lines.append(f"* context: {s.context}")
            if s.related_information:
                lines.append(f"* related information:\n{s.related_information}")
            lines.append("")  # Разделитель

        return SkillResult.ok("\n".join(lines).strip())

    @skill()
    async def update_mental_state(
        self,
        state_id: str,
        tier: Optional[Literal["high", "medium", "low", "background"]] = None,
        category: Optional[Literal["subject", "object"]] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        context: Optional[str] = None,
        related_information: Optional[str] = None,
    ) -> SkillResult:
        """Обновляет текущее состояние сущности в MentalState по её ID."""

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

            # Обновляем только переданные поля
            if tier:
                state.tier = tier
            if category:
                state.category = category
            if description:
                state.description = description
            if status:
                state.status = status
            if context is not None:
                state.context = context
            if related_information is not None:
                state.related_information = related_information

            # updated_at обновится автоматически благодаря onupdate в таблице
            await session.commit()

        msg = f"MentalState '{state.name}' (ID: {state_id}) обновлен."
        system_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    @skill()
    async def delete_mental_state(self, state_id: str) -> SkillResult:
        """Удаляет сущность из MentalState, если о ней больше не нужно помнить."""

        async with self.db.session_factory() as session:
            result = await session.execute(
                delete(MentalStateTable).where(MentalStateTable.id == state_id)
            )
            await session.commit()

            if result.rowcount == 0:
                return SkillResult.fail(f"MentalState с ID {state_id} не найден.")

        msg = f"MentalState с ID {state_id} удален."
        system_logger.info(f"[SQL DB] {msg}")
        return SkillResult.ok(msg)

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок для контекста агента.
        """
        res = await self.get_mental_states()
        return f"## MENTAL STATES\nMax number of entities that can be remembered:\n{self.max_entities}\n{res.message}"
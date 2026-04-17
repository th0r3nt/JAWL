import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import select, desc

from src.utils.logger import system_logger
from src.l1_databases.sql.tables import TickTable

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLTicks:
    """
    CRUD-функции для взаимодействия с таблицей логгирования тиков агента.
    Вызывается системой (ReAct циклом), а не самим агентом.
    """

    def __init__(self, db: "SQLDB"):
        self.db = db

    async def save_tick(
        self, thoughts: str, actions: list[dict[str, Any]], results: dict[str, Any]
    ) -> str:
        """Сохраняет один полный цикл (тик) работы агента."""
        tick_id = str(uuid.uuid4())

        async with self.db.session_factory() as session:
            new_tick = TickTable(
                id=tick_id, thoughts=thoughts, actions=actions, results=results
            )
            session.add(new_tick)
            await session.commit()

        system_logger.debug(f"[SQL DB] Тик сохранен (ID: {tick_id[:8]}).")
        return tick_id

    async def get_ticks(self, limit: int = 5) -> list[TickTable]:
        """
        Возвращает последние N тиков для инъекции в системный промпт (Context Builder).
        """
        async with self.db.session_factory() as session:
            # Сортируем по времени по убыванию, берем limit
            stmt = select(TickTable).order_by(desc(TickTable.created_at)).limit(limit)
            result = await session.execute(stmt)

            # Возвращаем в хронологическом порядке (от старых к новым)
            ticks = result.scalars().all()
            return list(reversed(ticks))

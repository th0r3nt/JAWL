import json
import uuid
from typing import TYPE_CHECKING, Any
from sqlalchemy import select, desc

from src.utils.logger import system_logger
from src.utils.dtime import format_datetime
from src.l1_databases.sql.tables import TickTable

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLTicks:
    """
    CRUD-функции для взаимодействия с таблицей логгирования тиков агента.
    """

    def __init__(
        self, db: "SQLDB", limit: int = 30, result_max_chars: int = 5000, tz_offset: int = 0
    ):
        self.db = db
        self.limit = limit
        self.result_max_chars = result_max_chars
        self.tz_offset = tz_offset

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
        Возвращает последние N тиков.
        """
        async with self.db.session_factory() as session:
            stmt = select(TickTable).order_by(desc(TickTable.created_at)).limit(limit)
            result = await session.execute(stmt)

            ticks = result.scalars().all()
            return list(reversed(ticks))

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный блок для контекста агента.
        """

        ticks = await self.get_ticks(limit=self.limit)

        if not ticks:
            return "## RECENT TICKS\nНет предыдущих тиков."

        blocks = []
        total_ticks = len(ticks)

        for i, t in enumerate(ticks):
            # Определяем, является ли этот тик самым последним (свежим)
            is_last_tick = i == total_ticks - 1

            # ПАРСИНГ ДЕЙСТВИЙ
            actions_list = []
            if isinstance(t.actions, list):
                for a in t.actions:
                    if isinstance(a, dict):
                        t_name = a.get("tool_name", "unknown")
                        params = a.get("parameters", {})
                        actions_list.append(
                            f"`{t_name}`({json.dumps(params, ensure_ascii=False)})"
                        )
                    else:
                        actions_list.append(str(a))

            elif isinstance(t.actions, dict):
                t_name = t.actions.get("tool_name", "unknown")
                params = t.actions.get("parameters", {})
                actions_list.append(f"`{t_name}`({json.dumps(params, ensure_ascii=False)})")

            else:
                actions_list.append(str(t.actions))

            actions_str = ", ".join(actions_list) if actions_list else "None"

            # Динамическая обрезка действий: 1500 символов для последнего, 500 для истории

            action_limit = 1500 if is_last_tick else 500
            if len(actions_str) > action_limit:
                actions_str = actions_str[:action_limit] + " ...[Параметры обрезаны]"

            # Парсинг результатов
            if t.results and isinstance(t.results, dict) and "execution_report" in t.results:
                res_str = str(t.results["execution_report"])

            elif t.results:
                res_str = json.dumps(t.results, ensure_ascii=False, indent=2)

            else:
                res_str = "None"

            # Динамическая обрезка результатов: лимит из конфига для последнего, 500 для истории
            res_limit = self.result_max_chars if is_last_tick else 500
            if len(res_str) > res_limit:
                res_str = (
                    res_str[:res_limit]
                    + f"\n...[Результат обрезан. Превышен лимит истории в {res_limit} символов]"
                )

            # Форматирование времени через нашу новую утилиту
            time_str = format_datetime(t.created_at, self.tz_offset)
            short_id = t.id[:8]

            blocks.append(
                f"#### [Tick ID: {short_id}] ({time_str})\n"
                f"*Thoughts*: {t.thoughts}\n"
                f"*Actions*: {actions_str}\n"
                f"*Result*:\n```\n{res_str}\n```"
            )

        return "## RECENT TICKS\n" + "\n\n".join(blocks)

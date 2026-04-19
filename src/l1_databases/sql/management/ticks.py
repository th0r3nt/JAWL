import re
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
        self,
        db: "SQLDB",
        limit: int = 15,
        detailed_ticks: int = 2,
        action_max_chars: int = 2000,
        result_max_chars: int = 5000,
        tz_offset: int = 0,
    ):
        self.db = db
        self.ticks_limit = limit
        self.detailed_ticks = detailed_ticks
        self.action_max_chars = action_max_chars
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

        ticks = await self.get_ticks(limit=self.ticks_limit)

        if not ticks:
            return "## RECENT TICKS\nНет предыдущих тиков."

        blocks = []
        total_ticks = len(ticks)

        for i, t in enumerate(ticks):
            # Проверяем, попадает ли тик в последние N детализированных
            is_detailed = i >= total_ticks - self.detailed_ticks

            # ПАРСИНГ ДЕЙСТВИЙ
            action_limit = self.action_max_chars if is_detailed else 150
            actions_list = []

            # Унифицируем к списку (защита от галлюцинаций LLM)
            actions_raw = t.actions
            if isinstance(actions_raw, dict):
                actions_raw = [actions_raw]
            elif not isinstance(actions_raw, list):
                actions_raw = [actions_raw]

            for a in actions_raw:
                if isinstance(a, dict):
                    t_name = a.get("tool_name", "unknown")
                    params = a.get("parameters", {})
                    act_str = f"`{t_name}`({json.dumps(params, ensure_ascii=False)})"
                else:
                    act_str = str(a)

                # Обрезаем каждое действие индивидуально
                if len(act_str) > action_limit:
                    act_str = act_str[:action_limit] + " ...[Параметры обрезаны]"

                actions_list.append(act_str)

            actions_str = "\n".join(actions_list) if actions_list else "None"

            # ПАРСИНГ РЕЗУЛЬТАТОВ
            res_limit = self.result_max_chars if is_detailed else 150

            if t.results and isinstance(t.results, dict) and "execution_report" in t.results:
                raw_report = str(t.results["execution_report"])

                # Разбиваем строку по маркеру "Action [...]: "
                parts = re.split(r"(?=^Action \[[^\]]+\]: )", raw_report, flags=re.MULTILINE)

                formatted_parts = []
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue

                    # Обрезаем каждый результат индивидуально
                    if len(part) > res_limit:
                        formatted_parts.append(
                            part[:res_limit]
                            + f"\n...[Результат обрезан. Лимит {res_limit} симв.]"
                        )
                    else:
                        formatted_parts.append(part)

                res_str = "\n".join(formatted_parts)

            elif t.results:
                res_str = json.dumps(t.results, ensure_ascii=False, indent=2)
                if len(res_str) > res_limit:
                    res_str = (
                        res_str[:res_limit]
                        + f"\n...[Результат обрезан. Лимит {res_limit} симв.]"
                    )
            else:
                res_str = "None"

            # Форматирование времени
            time_str = format_datetime(t.created_at, self.tz_offset)
            short_id = t.id[:8]

            blocks.append(
                f"#### [Tick ID: {short_id}] ({time_str})\n"
                f"*Thoughts*: {t.thoughts}\n"
                f"*Actions*:\n{actions_str}\n"
                f"*Result*:\n```\n{res_str}\n```"
            )

        return "## RECENT TICKS\n" + "\n\n".join(blocks)

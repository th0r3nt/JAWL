"""
Сборщик и форматировщик истории действий агента (Ticks).

Логирует каждый шаг ReAct-цикла и отвечает за умную компрессию старых шагов
в системном промпте (оставляя N последних шагов подробными, а остальные ужимая
по количеству символов для экономии контекста).
"""

import re
import json
import uuid
from typing import TYPE_CHECKING, Any, List
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
        thoughts_short_max_chars: int = 2000,
        action_short_max_chars: int = 300,
        result_short_max_chars: int = 300,
        tz_offset: int = 0,
    ) -> None:
        """
        Инициализирует контроллер тиков и задает жесткие лимиты на размер контекста.

        Args:
            db: Подключение к SQLite.
            limit: Максимальное количество тиков (шагов), отображаемых в промпте.
            detailed_ticks: Сколько самых свежих тиков выводить в детальном виде (без обрезки).
            action_max_chars: Лимит символов для свежих действий.
            result_max_chars: Лимит символов для свежих результатов.
            thoughts_short_max_chars: Лимит символов для сжатых мыслей.
            action_short_max_chars: Лимит символов для сжатых действий.
            result_short_max_chars: Лимит символов для сжатых результатов.
            tz_offset: Смещение временной зоны.
        """
        self.db = db
        self.ticks_limit = limit
        self.detailed_ticks = detailed_ticks

        self.action_max_chars = action_max_chars
        self.result_max_chars = result_max_chars

        self.thoughts_short_max_chars = thoughts_short_max_chars
        self.action_short_max_chars = action_short_max_chars
        self.result_short_max_chars = result_short_max_chars

        self.tz_offset = tz_offset

    async def save_tick(
        self, thoughts: str, actions: list[dict[str, Any]], results: dict[str, Any]
    ) -> str:
        """
        Сохраняет единичный такт работы агента в базу данных.

        Args:
            thoughts: Внутренний монолог и логика агента.
            actions: Массив вызванных инструментов и их параметров.
            results: Ответы от инструментов или текст Traceback/ошибок.

        Returns:
            Сгенерированный UUID сохраненного тика.
        """

        tick_id = str(uuid.uuid4())

        async with self.db.session_factory() as session:
            new_tick = TickTable(
                id=tick_id, thoughts=thoughts, actions=actions, results=results
            )
            session.add(new_tick)
            await session.commit()

        system_logger.debug(f"[SQL DB] Тик сохранен (ID: {tick_id[:8]}).")
        return tick_id

    async def get_ticks(self, limit: int = 5) -> List[TickTable]:
        """
        Возвращает последние N тиков из базы данных в хронологическом порядке.

        Args:
            limit: Сколько записей извлечь.

        Returns:
            Список объектов TickTable.
        """

        async with self.db.session_factory() as session:
            stmt = select(TickTable).order_by(desc(TickTable.created_at)).limit(limit)
            result = await session.execute(stmt)

            ticks = result.scalars().all()
            return list(reversed(ticks))

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Извлекает последние N тиков из базы и динамически сжимает их объем.
        Последние 'detailed_ticks' отдаются почти полностью, остальные жестко обрезаются
        до 'short_max_chars' для предотвращения переполнения контекстного окна LLM.

        Returns:
            Готовый Markdown блок 'RECENT TICKS' для инъекции в промпт.
        """

        ticks = await self.get_ticks(limit=self.ticks_limit)

        if not ticks:
            return "## RECENT TICKS\nНет предыдущих тиков."

        blocks = []
        total_ticks = len(ticks)

        for i, t in enumerate(ticks):
            is_detailed = i >= total_ticks - self.detailed_ticks

            # ===============================================================================
            # ПАРСИНГ МЫСЛЕЙ
            # ===============================================================================

            thoughts_str = t.thoughts
            if not is_detailed and len(thoughts_str) > self.thoughts_short_max_chars:
                thoughts_str = (
                    thoughts_str[: self.thoughts_short_max_chars]
                    + " ... [Мысли обрезаны системой]"
                )

            # ===============================================================================
            # ПАРСИНГ ДЕЙСТВИЙ
            # ===============================================================================

            action_limit = (
                self.action_max_chars if is_detailed else self.action_short_max_chars
            )
            actions_list = []

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

                if len(act_str) > action_limit:
                    act_str = act_str[:action_limit] + " ...[Параметры обрезаны]"

                actions_list.append(act_str)

            actions_str = "\n".join(actions_list) if actions_list else "None"

            # ===============================================================================
            # ПАРСИНГ РЕЗУЛЬТАТОВ ДЕЙСТВИЙ
            # ===============================================================================

            res_limit = self.result_max_chars if is_detailed else self.result_short_max_chars

            if t.results and isinstance(t.results, dict) and "execution_report" in t.results:
                raw_report = str(t.results["execution_report"])
                parts = re.split(r"(?=^Action \[[^\]]+\]: )", raw_report, flags=re.MULTILINE)

                formatted_parts = []
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue

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

            time_str = format_datetime(t.created_at, self.tz_offset)

            step_str = ""
            if t.results and "step" in t.results and "max_steps" in t.results:
                step_str = f"ReAct Step: {t.results['step']}/{t.results['max_steps']}\n"

            blocks.append(
                f"#### [Tick] {time_str}\n"
                f"{step_str}"
                f"*Thoughts*: '{thoughts_str}'\n\n"
                f"*Actions*:\n{actions_str}\n\n"
                f"*Result*:\n```\n{res_str}\n```"
            )

        return "## RECENT TICKS\n" + "\n\n\n".join(blocks)

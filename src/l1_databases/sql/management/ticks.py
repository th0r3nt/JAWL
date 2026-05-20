# ФАЙЛ: src/l1_databases/sql/management/ticks.py
"""
Сборщик и форматировщик истории действий агента (Ticks).

Логирует каждый шаг ReAct-цикла и отвечает за умную компрессию старых шагов
в системном промпте (оставляя N последних шагов подробными, а остальные ужимая
по количеству символов для экономии контекста).
"""

import json
import uuid
from typing import TYPE_CHECKING, Any, List
from sqlalchemy import select, desc
from datetime import datetime, timezone

from src.utils.dtime import format_datetime, get_timezone

from src.l1_databases.sql.tables import TickTable
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

if TYPE_CHECKING:
    from src.l1_databases.sql.db import SQLDB


class SQLTicks:
    """
    CRUD-функции для взаимодействия с таблицей логгирования тиков агента.
    Обеспечивает сохранение, извлечение и динамическое форматирование истории
    в зависимости от целевой подсистемы (Главный агент или Фоновые процессы).
    """

    def __init__(
        self,
        db: "SQLDB",
        high_ticks: int = 3,
        medium_ticks: int = 7,
        low_ticks: int = 20,
        action_max_chars: int = 2000,
        result_max_chars: int = 5000,
        thoughts_short_max_chars: int = 1000,
        action_short_max_chars: int = 100,
        result_short_max_chars: int = 200,
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
        self.high_ticks = high_ticks
        self.medium_ticks = medium_ticks
        self.low_ticks = low_ticks

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

            return list(reversed(result.scalars().all()))

    def _format_tick_entry(self, t: TickTable, tier: str) -> str:
        """
        Внутренний утилитарный метод для форматирования одного тика.

        Returns:
            Отформатированная Markdown-строка с мыслями, действиями и результатами.
        """
        time_str = format_datetime(t.created_at, self.tz_offset, "%m-%d %H:%M:%S")
        step_str = (
            f"\n[Step {t.results['step']}/{t.results['max_steps']}]"
            if t.results and "step" in t.results
            else ""
        )

        header = f"## TICK {time_str}{step_str}\n"

        thoughts_str = t.thoughts
        if tier in ("MEDIUM", "LOW") and len(thoughts_str) > self.thoughts_short_max_chars:
            thoughts_str = thoughts_str[: self.thoughts_short_max_chars] + "...[Truncated]"

        # Для LOW тиков возвращаем ТОЛЬКО мысли
        if tier == "LOW":
            return f"{header}\n### Thoughts:\n{thoughts_str}"

        # MEDIUM и HIGH
        action_limit = self.action_max_chars if tier == "HIGH" else self.action_short_max_chars
        actions_list = []
        actions_raw = t.actions if isinstance(t.actions, list) else [t.actions]

        for a in actions_raw:
            if isinstance(a, dict):
                t_name = a.get("tool_name", "unknown")
                params = a.get("parameters", {})
                act_str = f"* {t_name}({json.dumps(params, ensure_ascii=False)})"
            else:
                act_str = f"* {a}"
            if len(act_str) > action_limit:
                act_str = act_str[:action_limit] + "...[Truncated]"
            actions_list.append(act_str)

        actions_str = "\n".join(actions_list) if actions_list else "None"

        res_limit = self.result_max_chars if tier == "HIGH" else self.result_short_max_chars
        res_str = "None"
        if t.results:
            res_str = str(t.results.get("execution_report", t.results))
            if len(res_str) > res_limit:
                res_str = res_str[:res_limit] + f"...[Truncated limit {res_limit}]"

        return f"{header}\n### Thoughts: \n{thoughts_str} \n\n### Actions:\n{actions_str} \n\n### Result:\n{res_str}"

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Извлекает последние N тиков из базы и динамически сжимает их объем.
        Последние 'detailed_ticks' отдаются почти полностью, остальные жестко обрезаются
        до 'short_max_chars' для предотвращения переполнения контекстного окна LLM.

        Предназначено для использования Главным Агентом (Оркестратором).

        Returns:
            Готовый Markdown блок 'RECENT TICKS' для инъекции в промпт.
        """

        total_limit = self.high_ticks + self.medium_ticks + self.low_ticks
        ticks = await self.get_ticks(limit=total_limit)

        if not ticks:
            return "## RECENT TICKS\nEmpty."

        blocks = []
        total = len(ticks)
        for i, t in enumerate(ticks):
            distance_from_newest = total - 1 - i

            if distance_from_newest < self.high_ticks:
                tier = "HIGH"

            elif distance_from_newest < self.high_ticks + self.medium_ticks:
                tier = "MEDIUM"

            else:
                tier = "LOW"

            blocks.append(self._format_tick_entry(t, tier))

        return "## RECENT TICKS\n" + "\n\n".join(blocks)

    async def get_full_context_block(self, limit: int = 10) -> str:
        """
        Извлекает последние N тиков из базы БЕЗ применения жесткого исторического сжатия.
        Все запрошенные тики трактуются как 'detailed', что позволяет моделям видеть
        реальные результаты выполнения (results), а не только мысли.

        Предназначено для фоновых когнитивных процессов (Subconscious, Tree of Thoughts),
        которым критически важно видеть полные причинно-следственные связи.

        Args:
            limit: Максимальное количество извлекаемых тиков.

        Returns:
            Отформатированный Markdown лог действий.
        """

        ticks = await self.get_ticks(limit=limit)
        if not ticks:
            return "RECENT ACTIONS LOG\nEmpty."

        blocks = [self._format_tick_entry(t, "HIGH") for t in ticks]

        return "RECENT ACTIONS LOG\n" + "\n\n".join(blocks)

    @skill(swarm=[Subagents.ARCHIVIST])
    async def get_ticks_by_time(
        self, start_time: str, end_time: str, detail: bool = False
    ) -> SkillResult:
        """
        Retrieves ticks for a specific time period.
        Format 'YYYY-MM-DD HH:MM:SS'.

        detail: If True, returns full logs.
        """
        try:
            tz = get_timezone(self.tz_offset)
            
            dt_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            dt_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)

            # SQLite при сравнении фильтров в ORM работает со строками (без таймзон)
            # Поэтому мы переводим время в UTC и срезаем tzinfo (делаем naive datetime)
            utc_start = dt_start.astimezone(timezone.utc).replace(tzinfo=None)
            utc_end = dt_end.astimezone(timezone.utc).replace(tzinfo=None)

            if utc_start > utc_end:
                return SkillResult.fail("Ошибка: start_time не может быть позже end_time.")

            limit = 200  # Жесткий лимит на количество возвращаемых тиков, чтобы избежать перегрузки

            async with self.db.session_factory() as session:
                stmt = select(TickTable).where(
                    TickTable.created_at >= utc_start,
                    TickTable.created_at <= utc_end
                ).order_by(TickTable.created_at.asc()).limit(limit)

                result = await session.execute(stmt)
                ticks = result.scalars().all()

            if not ticks:
                return SkillResult.ok(f"За указанный период ({start_time} - {end_time}) тиков не найдено.")

            tier = "HIGH" if detail else "MEDIUM"
            blocks = [self._format_tick_entry(t, tier) for t in ticks]

            res_str = "\n\n".join(blocks)
            if len(ticks) == limit:
                res_str += f"\n\n... [Достигнут лимит вывода в {limit} тиков. Рекомендуется уточнить временной диапазон для более узкого поиска]"

            return SkillResult.ok(f"История тиков ({start_time} - {end_time}):\n\n{res_str}")

        except ValueError:
            return SkillResult.fail("Ошибка: Неверный формат времени. Используйте 'YYYY-MM-DD HH:MM:SS'.")
        except Exception as e:
            return SkillResult.fail(f"Внутренняя ошибка при поиске тиков: {e}")
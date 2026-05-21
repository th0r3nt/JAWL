"""
Collector and formatter of agent actions history (Ticks).

Logs every step of the ReAct loop and handles smart compression of older steps
in the system prompt (leaving the N latest steps detailed, while compressing the rest
by character count to save context space).
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
    CRUD functions for interacting with the agent's tick logging table.
    Handles saving, retrieving, and dynamic formatting of history
    depending on the target subsystem (Main Agent or Background Processes).
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
        Initializes the tick controller and sets strict limits on the context size.

        Args:
            db: Connection to SQLite.
            limit: Maximum number of ticks (steps) displayed in the prompt.
            detailed_ticks: How many of the freshest ticks to output in detailed form (no truncation).
            action_max_chars: Character limit for fresh actions.
            result_max_chars: Character limit for fresh results.
            thoughts_short_max_chars: Character limit for compressed thoughts.
            action_short_max_chars: Character limit for compressed actions.
            result_short_max_chars: Character limit for compressed results.
            tz_offset: Timezone offset.
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
        Saves a single tick of the agent's work to the database.

        Args:
            thoughts: Internal monologue and logic of the agent.
            actions: Array of invoked tools and their parameters.
            results: Responses from tools or Traceback/error text.

        Returns:
            Generated UUID of the saved tick.
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
        Returns the last N ticks from the database in chronological order.

        Args:
            limit: How many records to retrieve.

        Returns:
            List of TickTable objects.
        """

        async with self.db.session_factory() as session:
            stmt = select(TickTable).order_by(desc(TickTable.created_at)).limit(limit)
            result = await session.execute(stmt)

            return list(reversed(result.scalars().all()))

    def _format_tick_entry(self, t: TickTable, tier: str) -> str:
        """
        Internal helper method to format a single tick.

        Returns:
            Formatted Markdown string containing thoughts, actions, and results.
        """
        time_str = format_datetime(t.created_at, self.tz_offset, "%m-%d %H:%M:%S")
        step_str = (
            f"\n[Step {t.results['step']}/{t.results['max_steps']}]"
            if t.results and "step" in t.results
            else ""
        )

        header = f"\n\n## TICK {time_str}{step_str}\n"

        thoughts_str = t.thoughts
        if tier in ("MEDIUM", "LOW") and len(thoughts_str) > self.thoughts_short_max_chars:
            thoughts_str = thoughts_str[: self.thoughts_short_max_chars] + "...[Truncated]"

        # For LOW ticks we return ONLY thoughts
        if tier == "LOW":
            return f"{header}\n### Thoughts:\n{thoughts_str}"

        # MEDIUM and HIGH
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
        Extracts the last N ticks from the database and dynamically compresses their size.
        The last 'detailed_ticks' are returned almost entirely, the rest are strictly truncated
        to 'short_max_chars' to prevent overflowing the LLM context window.

        Intended for use by the Main Agent (Orchestrator).

        Returns:
            Finished Markdown block 'RECENT TICKS' for injection into the prompt.
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
        Extracts the last N ticks from the database WITHOUT applying strict historical compression.
        All requested ticks are treated as 'detailed', allowing models to see
        real execution results (results) rather than just thoughts.

        Intended for background cognitive processes (Subconscious, Tree of Thoughts),
        which critically need to see full cause-and-effect relationships.

        Args:
            limit: Maximum number of extracted ticks.

        Returns:
            Formatted Markdown actions log.
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

            # SQLite works with strings (naive datetimes) for comparisons in filters
            # Therefore we convert time to UTC and strip tzinfo (make it naive)
            utc_start = dt_start.astimezone(timezone.utc).replace(tzinfo=None)
            utc_end = dt_end.astimezone(timezone.utc).replace(tzinfo=None)

            if utc_start > utc_end:
                return SkillResult.fail("Error: start_time cannot be later than end_time.")

            limit = 200  # Hard limit on returned ticks count to avoid bloating the prompt

            async with self.db.session_factory() as session:
                stmt = (
                    select(TickTable)
                    .where(TickTable.created_at >= utc_start, TickTable.created_at <= utc_end)
                    .order_by(TickTable.created_at.asc())
                    .limit(limit)
                )

                result = await session.execute(stmt)
                ticks = result.scalars().all()

            if not ticks:
                return SkillResult.ok(
                    f"No ticks found for the specified period ({start_time} - {end_time})."
                )

            tier = "HIGH" if detail else "MEDIUM"
            blocks = [self._format_tick_entry(t, tier) for t in ticks]

            res_str = "\n\n".join(blocks)
            if len(ticks) == limit:
                res_str += f"\n\n... [Output limit of {limit} ticks reached. It is recommended to narrow the time range for a more focused search]"

            return SkillResult.ok(f"Tick history ({start_time} - {end_time}):\n\n{res_str}")

        except ValueError:
            return SkillResult.fail("Error: Invalid time format. Use 'YYYY-MM-DD HH:MM:SS'.")
        except Exception as e:
            return SkillResult.fail(f"Internal error searching ticks: {e}")

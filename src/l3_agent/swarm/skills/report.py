"""
Subagent Reporting Skill.

Allows background subagents to submit final results to the main coordinator
and triggers wakeup notifications in the central EventBus.
"""

import asyncio
import re
from pathlib import Path
from src.l3_agent.skills.registry import skill, SkillResult
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.logger import swarm_logger


class SubagentReport:
    """Skill designed strictly for subagents to commit final results."""

    def __init__(self, event_bus: EventBus, sandbox_dir: Path) -> None:
        """
        Initializes report tool.

        Args:
            event_bus: System event bus.
            sandbox_dir: Target output folder path.
        """

        self.bus = event_bus
        self.reports_dir = sandbox_dir / "_system" / "subagents"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_report_filename(subagent_id: str, role: str) -> str:
        """Generates safe and clean report filename conforming to regex bounds."""

        safe_id = re.fullmatch(r"[A-Za-z0-9_-]{1,64}", subagent_id or "")
        safe_role = re.fullmatch(r"[A-Za-z0-9_-]{1,64}", role or "")
        if not safe_id or not safe_role:
            raise ValueError("subagent_id and role must match regex [A-Za-z0-9_-].")

        return f"{role}_{subagent_id}.md"

    @skill(hidden=True)
    async def submit_final_report(
        self, subagent_id: str, role: str, report: str
    ) -> SkillResult:
        """
        Submits detailed final Markdown report to Main Agent.
        Mandatory call upon task completion to safely terminate subagent loop.
        """

        try:
            filename = self._safe_report_filename(subagent_id, role)
        except ValueError as e:
            return SkillResult.fail(f"Unsafe subagent report filename: {e}")

        file_path = (self.reports_dir / filename).resolve()
        reports_root = self.reports_dir.resolve()
        if not file_path.is_relative_to(reports_root):
            return SkillResult.fail("Unsafe subagent report path was rejected.")

        def _write() -> None:
            file_path.write_text(report, encoding="utf-8")

        await asyncio.to_thread(_write)
        swarm_logger.info(f"Subagent {role}_{subagent_id} report: \n\n'{report}'")

        log = f"[Swarm] Subagent {role}_{subagent_id} completed the task. Report compiled."
        swarm_logger.info(log)

        # Signals the main agent that the worker has finished
        await self.bus.publish(
            Events.SUBAGENT_TASK_COMPLETED,
            subagent_id=subagent_id,
            role=role,
            message=f"Subagent [{role}_{subagent_id}] completed the delegated task. Report saved to '{file_path}'.",
        )

        return SkillResult.ok(
            "Report successfully committed. Now return an empty actions list [] to gracefully conclude the cycle."
        )

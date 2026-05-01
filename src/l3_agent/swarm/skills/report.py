"""
Инструмент обратной связи субагентов.

Предоставляет субагентам системный навык для сдачи финального отчета.
После вызова генерирует событие в EventBus, которое будит главного агента
для проверки результатов работы роя.
"""

import asyncio
from pathlib import Path
from src.l3_agent.skills.registry import skill, SkillResult
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.logger import system_logger


class SubagentReport:
    """
    Навык, предназначенный строго для субагентов.
    Позволяет им завершить свою работу, передав отчет Оркестратору.
    """

    def __init__(self, event_bus: EventBus, sandbox_dir: Path) -> None:
        """
        Инициализирует навык отчета.

        Args:
            event_bus: Глобальная шина событий (для пробуждения главного агента).
            sandbox_dir: Папка песочницы, куда будут сохраняться сырые MD-отчеты.
        """
        
        self.bus = event_bus
        self.reports_dir = sandbox_dir / "_system" / "subagents"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    @skill(hidden=True)
    async def submit_final_report(
        self, subagent_id: str, role: str, report: str
    ) -> SkillResult:
        """
        Отправляет финальный подробный отчет о проделанной работе главному агенту.
        Обязательно к выводу когда задача полностью выполнена, чтобы завершить ваш рабочий процесс.

        Args:
            subagent_id: Ваш выданный системный ID (возьмите из первоначальной задачи).
            role: Ваша выданная роль (например, 'coder', 'web_researcher').
            report: Детальный Markdown-отчет о выполненной задаче и результатах.
        """

        file_path = self.reports_dir / f"{role}_{subagent_id}.md"

        def _write() -> None:
            file_path.write_text(report, encoding="utf-8")

        await asyncio.to_thread(_write)

        system_logger.info(
            f"[Swarm] Субагент {role}_{subagent_id} завершил работу. Отчет сформирован."
        )

        # Сигнализируем главному агенту, что раб закончил
        await self.bus.publish(
            Events.SUBAGENT_TASK_COMPLETED,
            subagent_id=subagent_id,
            role=role,
            message=f"Субагент [{role}_{subagent_id}] завершил делегированную задачу. Отчет сохранен в '{file_path}'.",
        )

        return SkillResult.ok(
            "Отчет успешно сохранен и передан главному агенту. Теперь необходимо вернуть пустой массив actions=[], чтобы штатно завершить работу."
        )

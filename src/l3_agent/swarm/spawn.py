"""
Навык-оркестратор (Swarm Manager).

Предоставляет главному агенту инструмент (скилл) `spawn_subagent`, через который
он может делегировать объемные задачи. Управляет пулом (семафором) запущенных воркеров
для защиты от перегрузки сети и Rate Limits (HTTP 429).
"""

import asyncio
import uuid
import traceback
from pathlib import Path

from src.utils.logger import system_logger
from src.utils.settings import SwarmConfig
from src.utils.token_tracker import TokenTracker

from src.l3_agent.llm.client import LLMClient

from src.l3_agent.skills.registry import skill, SkillResult, _REGISTRY

from src.l3_agent.swarm.roles import Subagents, SubagentRole
from src.l3_agent.swarm.prompt.builder import SwarmPromptBuilder
from src.l3_agent.swarm.context.builder import SwarmContextBuilder
from src.l3_agent.swarm.loop import SubagentLoop


class SwarmManager:
    """Менеджер подсистемы роя (Субагентов). Контролирует спавн и пулы воркеров."""

    def __init__(
        self,
        llm_client: LLMClient,
        swarm_config: SwarmConfig,
        root_dir: Path,
        token_tracker: TokenTracker,
    ) -> None:
        """
        Инициализирует менеджер роя.

        Args:
            llm_client: Выделенный клиент языковой модели для субагентов (часто с более дешевой моделью).
            swarm_config: Конфигурация подсистемы.
            root_dir: Корень проекта JAWL.
            token_tracker: Отслеживатель токенов.
        """

        self.llm = llm_client
        self.config = swarm_config
        self.tracker = token_tracker

        self.prompt_builder = SwarmPromptBuilder(root_dir)
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_workers)
        self.active_tasks: set[asyncio.Task] = set()

        # Динамически собираем доступные роли и их навыки из реестра (OCP)
        self.role_skills: dict[str, list[str]] = {}
        self.active_roles: dict[str, SubagentRole] = {}  # role_id -> SubagentRole

        for skill_name, data in _REGISTRY.items():
            for role_obj in data.get("swarm_roles", []):
                if role_obj.id not in self.role_skills:
                    self.role_skills[role_obj.id] = []
                self.role_skills[role_obj.id].append(skill_name)
                self.active_roles[role_obj.id] = role_obj

        # Формируем динамический докстринг с описанием ролей
        base_doc = (
            "Делегирует сложную и объемную задачу автономному субагенту. "
            "Он будет работать в фоне параллельно вам и вернет подробный отчет после завершения. "
            "Рекомендовано использовать для делегирования рутины или любых других задач."
        )  # Докстринг, который будет видеть LLM в навыке spawn_subagent

        if self.active_roles:
            roles_desc = ["Доступные роли в данный момент:"]
            for r_id, r_obj in self.active_roles.items():
                roles_desc.append(f"- '{r_id}' ({r_obj.name}): {r_obj.description}")
            roles_str = "\n".join(roles_desc)

        else:
            roles_str = "Внимание: нет доступных ролей (Не хватает системных интерфейсов)."

        if hasattr(self.spawn_subagent, "__func__"):
            self.spawn_subagent.__func__.__doc__ = f"{base_doc}\n\n{roles_str}"
        else:
            self.spawn_subagent.__doc__ = f"{base_doc}\n\n{roles_str}"

    @skill()
    async def spawn_subagent(self, role: str, task_description: str) -> SkillResult:
        """
        Запускает фонового субагента для выполнения задачи.
        Докстринг динамически переопределяется в __init__ (base_doc = ...), чтобы показать агенту активные роли.

        Args:
            role: ID роли субагента (например 'coder', 'web_researcher').
            task_description: Детальное поручение.
        """

        if not self.config.enabled:
            return SkillResult.fail(
                "Ошибка: Подсистема Swarm отключена в настройках (settings.yaml)."
            )

        if self.config.subagent_model == "unknown":
            return SkillResult.fail(
                "Ошибка: В настройках не указана модель для субагентов (subagent_model)."
            )

        target_role = Subagents.get_by_id(role)
        if not target_role or target_role.id not in self.active_roles:
            active_ids = list(self.active_roles.keys())
            return SkillResult.fail(
                f"Роль '{role}' сейчас недоступна. Возможные причины: опечатка или отключен необходимый системный интерфейс. Доступные роли: {active_ids}"
            )

        subagent_id = str(uuid.uuid4())[:8]

        task = asyncio.create_task(
            self._run_subagent_task(subagent_id, target_role, task_description)
        )
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

        return SkillResult.ok(
            f"Субагент {role}_{subagent_id} успешно запущен в фоне. Будет прислано системное уведомление, когда он закончит работу."
        )

    async def _run_subagent_task(
        self, subagent_id: str, role: SubagentRole, task_description: str
    ) -> None:
        """
        Фоновая корутина, контролирующая выполнение цикла субагента под защитой семафора.
        """

        try:
            actual_skills = self.role_skills.get(role.id, [])

            async with self.semaphore:
                # Передаем конфигурацию в сборщик контекста
                context_builder = SwarmContextBuilder(
                    role=role, allowed_skills=actual_skills, config=self.config.context_depth
                )

                loop = SubagentLoop(
                    subagent_id=subagent_id,
                    role=role,
                    task_description=task_description,
                    llm_client=self.llm,
                    model_name=self.config.subagent_model,
                    prompt_builder=self.prompt_builder,
                    context_builder=context_builder,
                    allowed_skills=actual_skills,
                    token_tracker=self.tracker,
                    max_steps=self.config.context_depth.max_steps,
                )

                await loop.run()
        except Exception:
            system_logger.error(
                f"[Swarm] Критическая ошибка в фоновой задаче субагента {role.id}_{subagent_id}:\n{traceback.format_exc()}"
            )

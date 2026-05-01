"""
Сборщик динамического контекста для субагентов.

В отличие от главного агента, субагенты не имеют доступа к L0 State (перепискам,
статусам систем и т.д.). Этот модуль генерирует для них легковесный Stateless-контекст,
включающий только саму задачу, доступные инструменты и их собственную локальную историю действий.
"""

from typing import List, Dict
from src.l3_agent.skills.registry import _REGISTRY
from src.l3_agent.swarm.roles import SubagentRole
from src.utils.settings import SwarmContextDepthConfig


class SwarmContextBuilder:
    """Сборщик легковесного контекста для субагентов (Stateless + локальная история)."""

    def __init__(
        self, role: SubagentRole, allowed_skills: List[str], config: SwarmContextDepthConfig
    ) -> None:
        """
        Инициализирует сборщик контекста субагента.

        Args:
            role: Роль текущего субагента.
            allowed_skills: Список разрешенных для этой роли навыков (RBAC).
            config: Настройки глубины контекста (лимиты на обрезку текста).
        """
        self.role = role
        # Всегда добавляем навык отправки отчета
        self.allowed_skills = allowed_skills + ["SubagentReport.submit_final_report"]
        self.config = config

    def build(
        self, subagent_id: str, task_description: str, history: List[Dict[str, str]]
    ) -> str:
        """
        Собирает Markdown-текст (User Prompt) для текущего шага субагента.

        Args:
            subagent_id: Уникальный идентификатор воркера.
            task_description: Текст порученной задачи.
            history: Локальный лог всех действий и ответов субагента за прошлые шаги.

        Returns:
            Готовая строка контекста.
        """
        # Вытаскиваем документацию только тех скиллов, которые разрешены этой роли
        skills_docs = []
        for skill_name in self.allowed_skills:
            if skill_name in _REGISTRY:
                skills_docs.append(_REGISTRY[skill_name]["doc_string"])

        skills_str = "\n".join(skills_docs) if skills_docs else "Инструменты недоступны."

        history_blocks = []

        # Ограничиваем общую длину истории (гарантия, что мы не превысим max_steps)
        history = history[-self.config.max_steps :]
        total_history = len(history)

        for idx, step in enumerate(history):
            step_num = idx + 1
            # Вычисляем, является ли шаг "свежим" (детальным)
            is_detailed = (total_history - idx) <= self.config.detailed_steps

            thoughts = step["thoughts"]
            actions = step["actions"]
            results = step["results"]

            # Применяем лимиты в зависимости от давности шага
            if is_detailed:
                a_limit = self.config.action_max_chars
                r_limit = self.config.result_max_chars
                t_limit = 100000  # Свежие мысли не режем вообще
            else:
                a_limit = self.config.action_short_max_chars
                r_limit = self.config.result_short_max_chars
                t_limit = self.config.thoughts_short_max_chars

            def _truncate(text: str, limit: int, name: str) -> str:
                if len(text) > limit:
                    return (
                        text[:limit]
                        + f"\n... [{name} обрезаны системой сжатия контекста (> {limit} симв.)]"
                    )
                return text

            thoughts = _truncate(thoughts, t_limit, "Мысли")
            actions = _truncate(actions, a_limit, "Действия")
            results = _truncate(results, r_limit, "Результаты")

            history_blocks.append(
                f"### STEP {step_num}\n"
                f"*Thoughts*: {thoughts}\n"
                f"*Actions*:\n{actions}\n"
                f"*Results*:\n```\n{results}\n```"
            )

        history_str = (
            "\n\n".join(history_blocks) if history_blocks else "Пока нет истории действий."
        )

        return f"""
## SYSTEM INFO
- Your Subagent ID: {subagent_id}
- Your Role: {self.role.name.upper()}

## DELEGATED TASK
{task_description}

## AVAILABLE SKILLS
Выданы инструменты, которые соответствуют вашей роли.
{skills_str}

## EXECUTION HISTORY
{history_str}
""".strip()

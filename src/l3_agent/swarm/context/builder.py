from typing import List, Dict
from src.l3_agent.skills.registry import _REGISTRY
from src.l3_agent.swarm.roles import SubagentRole

class SwarmContextBuilder:
    """Сборщик легковесного контекста для субагентов (Stateless + локальная история)."""

    def __init__(self, role: SubagentRole, allowed_skills: List[str]):
        self.role = role
        # Всегда добавляем навык отправки отчета
        self.allowed_skills = allowed_skills + ["SubagentReport.submit_final_report"]

    def build(
        self, subagent_id: str, task_description: str, history: List[Dict[str, str]]
    ) -> str:
        # Вытаскиваем документацию только тех скиллов, которые разрешены этой роли
        skills_docs = []
        for skill_name in self.allowed_skills:
            if skill_name in _REGISTRY:
                skills_docs.append(_REGISTRY[skill_name]["doc_string"])

        skills_str = "\n".join(skills_docs) if skills_docs else "Инструменты недоступны."

        history_blocks = []
        for idx, step in enumerate(history, 1):
            history_blocks.append(
                f"### STEP {idx}\n"
                f"*Thoughts*: {step['thoughts']}\n"
                f"*Actions*: {step['actions']}\n"
                f"*Results*:\n```\n{step['results']}\n```"
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

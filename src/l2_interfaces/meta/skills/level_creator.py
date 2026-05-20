"""
Навыки саморасширения (Access Level 3: CREATOR).

Уровень бога. Позволяет агенту динамически внедрять собственные Python-скрипты,
написанные им в песочнице, как нативные инструменты фреймворка (Dynamic Skill Injection).
Также позволяет рисовать кастомные дашборды.
"""

from typing import Dict

from src.utils.event.registry import Events

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.skills.custom import CustomSkillsRegistry


class MetaCreator:
    """Уровень 3 (CREATOR). Регистрация скриптов агента как нативных навыков."""

    def __init__(self, meta_client: MetaClient, registry: CustomSkillsRegistry) -> None:
        self.client = meta_client
        self.registry = registry

    @skill()
    async def register_custom_skill(
        self,
        skill_name: str,
        description: str,
        filepath: str,
        func_name: str,
        parameters_dict: Dict[str, str],
    ) -> SkillResult:
        """
        Compiles proxy wrapper for sandbox function and injects it as native tool. 
        
        skill_name: Desired callable name. 
        filepath: Relative sandbox path. 
        func_name: Target function name. 
        parameters_dict: JSON schema args.
        """

        success, result_or_err = self.registry.register_skill(
            skill_name, description, filepath, func_name, parameters_dict
        )

        if success:
            return SkillResult.ok(
                f"Кастомный навык '{result_or_err}' успешно зарегистрирован и теперь доступен для вызова."
            )
        return SkillResult.fail(f"Ошибка регистрации навыка: {result_or_err}")

    @skill()
    async def remove_custom_skill(self, skill_name: str) -> SkillResult:
        """
        Removes previously created custom skill by full name.
        """
        success, err = self.registry.unregister_skill(skill_name)

        if success:
            return SkillResult.ok(f"Навык '{skill_name}' успешно удален из системы.")
        return SkillResult.fail(f"Ошибка удаления навыка: {err}")

    @skill()
    async def get_custom_skills(self) -> SkillResult:
        """
        Returns list of all registered custom skills and their mappings.
        """
        
        skills = self.registry.get_all_skills()
        if not skills:
            return SkillResult.ok("Список кастомных навыков пуст.")

        lines = ["Зарегистрированные интеграции:"]
        for s_name, info in skills.items():
            params_str = ", ".join([f"{k}: {v}" for k, v in info.get("params", {}).items()])
            lines.append(
                f"- {s_name} | Файл: {info['filepath']}::{info['func_name']} | Параметры: {{{params_str}}}"
            )

        return SkillResult.ok("\n".join(lines))

    @skill()
    async def set_dashboard_block(self, name: str, markdown_content: str) -> SkillResult:
        """
        Injects static Markdown block into system context. 
        
        name: Unique dashboard title. 
        markdown_content: Block content.
        """

        await self.client.bus.publish(
            Events.SYSTEM_DASHBOARD_UPDATE, name=name, content=markdown_content
        )
        return SkillResult.ok(f"Дашборд '{name}' успешно обновлен.")

    @skill()
    async def remove_dashboard_block(self, name: str) -> SkillResult:
        """
        Removes custom block from system context.
        """
        
        await self.client.bus.publish(Events.SYSTEM_DASHBOARD_UPDATE, name=name, content="")
        return SkillResult.ok(f"Дашборд '{name}' удален.")

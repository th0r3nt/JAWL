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
        Компилирует прокси-обертку (Proxy) для функции из песочницы и
        внедряет её в ядро агента как полноправный инструмент.

        Args:
            skill_name: Желаемое имя для вызова (префикс 'Custom.' добавится системой).
            description: Инструкция, объясняющая, зачем вызывать эту функцию.
            filepath: Относительный путь к скрипту в 'sandbox/'.
            func_name: Имя целевой функции внутри скрипта.
            parameters_dict: JSON-схема аргументов (например, `{"limit": "int = 10"}`).
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
        Удаляет созданный ранее кастомный навык по его полному имени.

        Args:
            skill_name: Имя навыка (включая 'Custom.').
        """
        success, err = self.registry.unregister_skill(skill_name)

        if success:
            return SkillResult.ok(f"Навык '{skill_name}' успешно удален из системы.")
        return SkillResult.fail(f"Ошибка удаления навыка: {err}")

    @skill()
    async def get_custom_skills(self) -> SkillResult:
        """
        Возвращает список всех зарегистрированных кастомных навыков и их маппинг.
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
        Инжектит статический Markdown-блок прямо в приборную панель (L0 State).
        Используется для создания кастомных "мониторов" (цены, статусы серверов, ToDo-листы).

        Args:
            name: Уникальный заголовок дашборда.
            markdown_content: Содержимое блока (будет отрисовано в системном промпте).
        """
        await self.client.bus.publish(
            Events.SYSTEM_DASHBOARD_UPDATE, name=name, content=markdown_content
        )
        return SkillResult.ok(f"Дашборд '{name}' успешно обновлен.")

    @skill()
    async def remove_dashboard_block(self, name: str) -> SkillResult:
        """
        Удаляет кастомный блок из системного контекста (полностью очищая его содержимое).

        Args:
            name: Заголовок удаляемого дашборда.
        """
        await self.client.bus.publish(Events.SYSTEM_DASHBOARD_UPDATE, name=name, content="")
        return SkillResult.ok(f"Дашборд '{name}' удален.")

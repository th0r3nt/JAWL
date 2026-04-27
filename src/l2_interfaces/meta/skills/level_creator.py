from typing import Dict

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.skills.custom import CustomSkillsRegistry


class MetaCreator:
    """Уровень 3 (CREATOR). Регистрация скриптов агента как нативных навыков."""

    def __init__(self, meta_client: MetaClient, registry: CustomSkillsRegistry):
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
        [3/CREATOR] Регистрирует астомную функцию из песочницы (sandbox/) как нативный навык.
        Функция обязана возвращать словарь (JSON).

        - skill_name: Имя кастомного навыка для добавления(напр. 'SocialNetwork.create_post'). Префикс 'Custom.' добавится автоматически.
        - filepath: Путь к скрипту в sandbox/ (напр. 'sandbox/social_network/api.py').
        - func_name: Имя вызываемой функции внутри скрипта (Напр. create_post). Рекомендуется написать докстринг для этой функции заранее.
        - parameters_dict: Словарь аргументов. Ключ - имя аргумента, значение - описание/тип (например: {'title': 'str', 'content': 'str = None'}).
        """
        success, result_or_err = self.registry.register_skill(
            skill_name, description, filepath, func_name, parameters_dict
        )

        if success:
            return SkillResult.ok(
                f"Кастомный навык '{result_or_err}' успешно зарегистрирован и теперь доступен для вызов."
            )
        return SkillResult.fail(f"Ошибка регистрации навыка: {result_or_err}")

    @skill()
    async def remove_custom_skill(self, skill_name: str) -> SkillResult:
        """
        [3/CREATOR] Удаляет созданный ранее кастомный навык по его полному имени (включая 'Custom.').
        """

        success, err = self.registry.unregister_skill(skill_name)

        if success:
            return SkillResult.ok(f"Навык '{skill_name}' успешно удален из системы.")
        return SkillResult.fail(f"Ошибка удаления навыка: {err}")

    @skill()
    async def get_custom_skills(self) -> SkillResult:
        """
        [3/CREATOR] Возвращает список всех зарегистрированных кастомных навыков и их маппинг.
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

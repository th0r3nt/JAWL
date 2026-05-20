"""
Навыки Meta уровня 0 (SAFE).

Базовые, самые безопасные настройки системы.
Позволяют агенту изменять свою рабочую модель LLM (переключать личности/провайдеров)
и настраивать уровень креативности (Temperature).
"""

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill


class MetaSafe:
    """Уровень 0 (SAFE). Базовые настройки системы."""

    def __init__(self, meta_client: MetaClient) -> None:
        self.client = meta_client

    @skill()
    async def change_model(self, model_name: str) -> SkillResult:
        """
        Changes currently active LLM model.
        """

        if self.client.available_models and model_name not in self.client.available_models:
            return SkillResult.fail(
                f"Модель '{model_name}' недоступна. Необходимо выбрать из списка: {self.client.available_models}"
            )

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "main_model"], model_name
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении файла конфигурации.")

        self.client.agent_state.llm_model = model_name
        return SkillResult.ok("True")

    @skill()
    async def add_available_model(self, model_name: str) -> SkillResult:
        """
        Adds new LLM model to available models list.
        """

        if model_name in self.client.available_models:
            return SkillResult.ok("True")

        new_list = list(self.client.available_models)
        new_list.append(model_name)

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "available_models"], new_list
        )
        if not success:
            return SkillResult.fail("Ошибка при обновлении конфигурации.")

        self.client.available_models = new_list
        return SkillResult.ok("True")

    @skill()
    async def remove_available_model(self, model_name: str) -> SkillResult:
        """
        Removes LLM model from available list.
        """

        if model_name not in self.client.available_models:
            return SkillResult.fail(f"Ошибка: Модели '{model_name}' нет в списке.")

        if model_name == self.client.agent_state.llm_model:
            return SkillResult.fail(
                "Ошибка: Нельзя удалить модель, которая используется в данный момент."
            )

        new_list = [m for m in self.client.available_models if m != model_name]

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "available_models"], new_list
        )
        if not success:
            return SkillResult.fail("Ошибка при обновлении конфигурации.")

        self.client.available_models = new_list
        return SkillResult.ok("True")

    @skill()
    async def change_temperature(self, temperature: float) -> SkillResult:
        """
        Changes LLM generation temperature parameter.
        """

        if not 0.0 <= temperature <= 2.0:
            return SkillResult.fail("Температура должна быть в пределах от 0.0 до 2.0.")

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "temperature"], temperature
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении конфигурации.")

        self.client.agent_state.temperature = temperature
        return SkillResult.ok("True")

    @skill()
    async def set_current_goal(self, goal: str) -> SkillResult:
        """
        Sets current focus goal. 
        Pins goal in system prompt to maintain context over long cycles. 
        Pass empty string to clear.
        """
        
        clean_goal = goal.strip()
        self.client.agent_state.current_goal = clean_goal

        if clean_goal:
            return SkillResult.ok("True")
        return SkillResult.ok("True")

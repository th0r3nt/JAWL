from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill


class MetaSafe:
    """Уровень 0 (SAFE). Самые безопасные настройки системы."""

    def __init__(self, meta_client: MetaClient):
        self.client = meta_client

    @skill()
    async def change_model(self, model_name: str) -> SkillResult:
        """[0/SAFE] Изменяет используемую LLM модель."""

        if self.client.available_models and model_name not in self.client.available_models:
            return SkillResult.fail(
                f"Модель '{model_name}' недоступна. Необходимо выбрать из списка: {self.client.available_models}"
            )

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "model"], model_name
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении файла конфигурации.")

        self.client.agent_state.llm_model = model_name
        return SkillResult.ok(f"Модель успешно изменена на {model_name}.")

    @skill()
    async def add_available_model(self, model_name: str) -> SkillResult:
        """[0/SAFE] Добавляет новую LLM модель в список доступных (available_models)."""

        if model_name in self.client.available_models:
            return SkillResult.ok(f"Модель '{model_name}' уже есть в списке доступных.")

        new_list = list(self.client.available_models)
        new_list.append(model_name)

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "available_models"], new_list
        )
        if not success:
            return SkillResult.fail("Ошибка при обновлении конфигурации.")

        self.client.available_models = new_list
        return SkillResult.ok(f"Модель '{model_name}' добавлена в список доступных.")

    @skill()
    async def remove_available_model(self, model_name: str) -> SkillResult:
        """[0/SAFE] Удаляет LLM модель из списка доступных (available_models)."""

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
        return SkillResult.ok(f"Модель '{model_name}' удалена из списка доступных.")

    @skill()
    async def change_temperature(self, temperature: float) -> SkillResult:
        """[0/SAFE] Изменяет temperature языковой модели (от 0.0 до 1.0)."""

        if not 0.0 <= temperature <= 2.0:
            return SkillResult.fail("Температура должна быть в пределах от 0.0 до 2.0.")

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "temperature"], temperature
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении конфигурации.")

        self.client.agent_state.temperature = temperature
        return SkillResult.ok(f"Температура успешно изменена на {temperature}.")

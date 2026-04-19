from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.event.registry import Events


class MetaConfiguration:
    def __init__(self, meta_client: MetaClient):
        self.client = meta_client

    @skill()
    async def change_model(self, model_name: str) -> SkillResult:
        """Изменяет используемую агентом языковую модель (LLM)."""

        success = await self.client.update_setting(
            ["llm", "model_name"], model_name, f"Модель изменена на {model_name}"
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении файла конфигурации.")

        self.client.agent_state.llm_model = model_name
        return SkillResult.ok(f"Модель успешно изменена на {model_name}.")

    @skill()
    async def change_temperature(self, temperature: float) -> SkillResult:
        """Изменяет temperature языковой модели (от 0.0 до 1.0)."""

        success = await self.client.update_setting(
            ["llm", "temperature"], temperature, f"Temperature изменена на {temperature}"
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении конфигурации.")

        self.client.agent_state.temperature = temperature
        return SkillResult.ok(f"Температура успешно изменена на {temperature}.")

    @skill()
    async def change_max_react_steps(self, steps: int) -> SkillResult:
        """Изменяет максимальное количество шагов в одном цикле ReAct."""

        success = await self.client.update_setting(
            ["llm", "max_react_steps"], steps, f"Лимит ReAct изменен на {steps}"
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении конфигурации.")

        self.client.agent_state.max_react_steps = steps
        return SkillResult.ok(f"Лимит шагов изменен на {steps}.")

    @skill()
    async def change_heartbeat_interval(self, interval_sec: int) -> SkillResult:
        """Изменяет интервал между пробуждениями агента (в секундах)."""

        success = await self.client.update_setting(
            path_keys=["system", "heartbeat_interval"],
            new_value=interval_sec,
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении конфигурации.")

        self.client.agent_state.heartbeat_interval = interval_sec

        # Публикуем событие для L3 (Heartbeat)
        await self.client.bus.publish(
            Events.SYSTEM_CONFIG_UPDATED, key="heartbeat_interval", value=interval_sec
        )
        return SkillResult.ok(
            f"Интервал изменен на {interval_sec} сек."
        )

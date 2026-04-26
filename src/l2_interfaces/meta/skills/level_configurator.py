from pathlib import Path
from typing import Literal

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.event.registry import Events


class MetaConfigurator:
    """Уровень 1 (CONFIGURATOR). Управление базами данных, контекстом и собственными промптами."""

    def __init__(self, meta_client: MetaClient, root_dir: Path):
        self.client = meta_client
        self.custom_prompts_dir = root_dir / "src" / "l3_agent" / "prompt" / "custom"
        self.custom_prompts_dir.mkdir(parents=True, exist_ok=True)

    @skill()
    async def change_heartbeat_interval(self, interval_sec: int) -> SkillResult:
        """
        [1/CONFIGURATOR] Изменяет Heartbeat интервал между пробуждениями агента (в секундах).
        """

        success = await self.client.update_yaml(
            self.client.settings_path, ["system", "heartbeat_interval"], interval_sec
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении конфигурации.")

        self.client.agent_state.heartbeat_interval = interval_sec
        await self.client.bus.publish(
            Events.SYSTEM_CONFIG_UPDATED, key="heartbeat_interval", value=interval_sec
        )
        return SkillResult.ok(f"Интервал успешно изменен на {interval_sec} сек.")

    @skill()
    async def change_max_react_steps(self, steps: int) -> SkillResult:
        """
        [1/CONFIGURATOR] Изменяет максимальное количество шагов в одном цикле ReAct.
        """

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "max_react_steps"], steps
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении конфигурации.")

        self.client.agent_state.max_react_steps = steps
        return SkillResult.ok(f"Лимит шагов успешно изменен на {steps}.")

    @skill()
    async def change_database_limits(
        self,
        database: Literal["tasks", "personality_traits", "mental_states", "drives_custom"],
        new_limit: int,
    ) -> SkillResult:
        """
        [1/CONFIGURATOR] Изменяет лимиты для различных SQL-модулей памяти.
        """

        db_keys_map = {
            "tasks": ["system", "sql", "tasks", "max_tasks"],
            "personality_traits": ["system", "sql", "personality_traits", "max_traits"],
            "mental_states": ["system", "sql", "mental_states", "max_entities"],
            "drives_custom": ["system", "sql", "drives", "max_custom_drives"],
        }

        path_keys = db_keys_map.get(database)
        success = await self.client.update_yaml(
            self.client.settings_path, path_keys, new_limit
        )

        if success:
            # Моментальное обновление в памяти
            await self.client.bus.publish(
                Events.SYSTEM_CONFIG_UPDATED, key="db_limit", module=database, value=new_limit
            )
            return SkillResult.ok(
                f"Лимит базы данных '{database}' успешно изменен на {new_limit}. Изменения применены."
            )
        return SkillResult.fail("Ошибка обновления конфигурации.")

    @skill()
    async def change_context_depth(self, total_ticks: int, detailed_ticks: int) -> SkillResult:
        """
        [1/CONFIGURATOR] Меняет глубину памяти о последних действиях (сколько тиков помнить).
        total_ticks: общее количество.
        detailed_ticks: количество последних n тиков, контекст которых хранить детально.
        """

        if detailed_ticks > total_ticks:
            return SkillResult.fail("detailed_ticks не может быть больше чем total_ticks.")

        s1 = await self.client.update_yaml(
            self.client.settings_path, ["system", "context_depth", "ticks"], total_ticks
        )
        s2 = await self.client.update_yaml(
            self.client.settings_path,
            ["system", "context_depth", "detailed_ticks"],
            detailed_ticks,
        )

        if s1 and s2:
            # Обновляем AgentState (чтобы агент видел в промпте)
            self.client.agent_state.context_ticks = total_ticks
            self.client.agent_state.context_detailed_ticks = detailed_ticks

            # Обновляем сами классы БД через EventBus
            await self.client.bus.publish(
                Events.SYSTEM_CONFIG_UPDATED,
                key="context_depth",
                total_ticks=total_ticks,
                detailed_ticks=detailed_ticks,
            )
            return SkillResult.ok(
                f"Глубина контекста изменена (Общие: {total_ticks}, Детальные: {detailed_ticks}). Изменения применены."
            )
        return SkillResult.fail("Ошибка сохранения настроек.")

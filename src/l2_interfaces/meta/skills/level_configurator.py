"""
Навыки Meta уровня 1 (CONFIGURATOR).

Позволяют агенту изменять настройки собственного "мозга": глубину памяти
(лимиты контекста и БД) и ритм авто-пробуждений (Heartbeat).
"""

from pathlib import Path
from typing import Literal

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.event.registry import Events


class MetaConfigurator:
    """Уровень 1 (CONFIGURATOR). Управление базами данных, контекстом и промптами."""

    def __init__(self, meta_client: MetaClient, root_dir: Path) -> None:
        self.client = meta_client
        self.custom_prompts_dir = root_dir / "src" / "l3_agent" / "prompt" / "custom"
        self.custom_prompts_dir.mkdir(parents=True, exist_ok=True)

    @skill()
    async def change_heartbeat_interval(self, interval_sec: int) -> SkillResult:
        """
        Changes Heartbeat interval between wakeups.
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
        return SkillResult.ok("True")

    @skill()
    async def change_max_react_steps(self, steps: int) -> SkillResult:
        """
        Changes max steps allowed in single ReAct cycle.
        """

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "max_react_steps"], steps
        )
        if not success:
            return SkillResult.fail("Ошибка при сохранении конфигурации.")

        self.client.agent_state.max_react_steps = steps
        return SkillResult.ok("True")

    @skill()
    async def change_database_limits(
        self,
        database: Literal["tasks", "personality_traits", "mental_states", "drives_custom"],
        new_limit: int,
    ) -> SkillResult:
        """
        Changes row limits for specific SQL modules.
        """

        db_keys_map = {
            "tasks": ["system", "db", "sql", "tasks", "max_tasks"],
            "personality_traits": ["system", "db", "sql", "personality_traits", "max_traits"],
            "mental_states": ["system", "db", "sql", "mental_states", "max_entities"],
            "drives_custom": ["system", "db", "sql", "drives", "max_custom_drives"],
        }

        path_keys = db_keys_map.get(database)
        if not path_keys:
            return SkillResult.fail("Неверное имя базы данных.")

        success = await self.client.update_yaml(
            self.client.settings_path, path_keys, new_limit
        )

        if success:
            # Моментальное обновление в памяти
            await self.client.bus.publish(
                Events.SYSTEM_CONFIG_UPDATED, key="db_limit", module=database, value=new_limit
            )
            return SkillResult.ok("True")
        return SkillResult.fail("Ошибка обновления конфигурации.")

    @skill()
    async def change_context_depth(
        self, high_ticks: int, medium_ticks: int, low_ticks: int
    ) -> SkillResult:
        """
        Dynamically alters context window depth. 
        
        high_ticks: Uncut recent ticks. 
        medium_ticks: Ticks with truncated I/O. 
        low_ticks: Thoughts only.
        """
        
        s1 = await self.client.update_yaml(
            self.client.settings_path, ["system", "context_depth", "high_ticks"], high_ticks
        )
        s2 = await self.client.update_yaml(
            self.client.settings_path,
            ["system", "context_depth", "medium_ticks"],
            medium_ticks,
        )
        s3 = await self.client.update_yaml(
            self.client.settings_path, ["system", "context_depth", "low_ticks"], low_ticks
        )

        if s1 and s2 and s3:
            self.client.agent_state.context_high_ticks = high_ticks
            self.client.agent_state.context_medium_ticks = medium_ticks
            self.client.agent_state.context_low_ticks = low_ticks

            await self.client.bus.publish(
                Events.SYSTEM_CONFIG_UPDATED,
                key="context_depth",
                high_ticks=high_ticks,
                medium_ticks=medium_ticks,
                low_ticks=low_ticks,
            )
            return SkillResult.ok("True")
        return SkillResult.fail("Ошибка сохранения настроек.")

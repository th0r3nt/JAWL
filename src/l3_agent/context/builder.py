import json
import asyncio
from typing import TYPE_CHECKING, Any, Dict

from src.l3_agent.skills.registry import get_skills_library

if TYPE_CHECKING:
    from src.l0_state.interfaces.state import (
        HostOSState,
        TelethonState,
        AiogramState,
        HostTerminalState,
    )
    from src.l0_state.agent.state import AgentState

    from src.l1_databases.sql.management.ticks import SQLTicks
    from src.l1_databases.sql.management.tasks import SQLTasks
    from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits


class ContextBuilder:
    """
    Отвечает за сборку динамического контекста для каждого вызова к LLM.
    """

    def __init__(
        self,
        host_os_state: "HostOSState",
        telethon_state: "TelethonState",
        aiogram_state: "AiogramState",
        terminal_state: "HostTerminalState",
        agent_state: "AgentState",
        sql_ticks: "SQLTicks",
        sql_tasks: "SQLTasks",
        sql_traits: "SQLPersonalityTraits",
    ):
        # Статус интерфейсов
        self.host_os_state = host_os_state
        self.telethon_state = telethon_state
        self.aiogram_state = aiogram_state
        self.terminal_state = terminal_state

        # Статус агента
        self.agent_state = agent_state

        # БАЗЫ ДАННЫХ
        self.sql_ticks = sql_ticks
        self.sql_tasks = sql_tasks
        self.sql_traits = sql_traits

    async def build(
        self, event_name: str, payload: Dict[str, Any], tick_limit: int = 5
    ) -> str:
        """Собирает готовый контекст для агента."""

        # Собираем данные из БД параллельно для ускорения работы
        traits_task = self._build_personality_traits()
        tasks_task = self._build_tasks()
        ticks_task = self._build_recent_ticks(tick_limit)

        personality_traits, tasks, recent_ticks = await asyncio.gather(
            traits_task, tasks_task, ticks_task
        )

        skills = self._build_skills()
        state = self._build_state()
        wake_up_reason = self._build_wake_up_reason(event_name, payload)

        return f"""
## PERSONALITY TRAITS
{personality_traits}

## SKILLS
{skills}

## TASKS
{tasks}

## STATE
{state}

## RECENT TICKS
{recent_ticks}

## WAKE UP REASON
{wake_up_reason}
""".strip()

    # ===================================================
    # СБОРКА КОНТЕКСТА
    # ===================================================

    async def _build_personality_traits(self) -> str:
        """Собирает блок черт личности агента."""
        res = await self.sql_traits.get_traits()
        return res.message

    def _build_skills(self) -> str:
        """Собирает блок доступных скиллов."""
        # Берем уже готовую документацию прямо из реестра
        return get_skills_library()

    async def _build_tasks(self) -> str:
        """Собирает блок долгосрочных задач агента."""
        res = await self.sql_tasks.get_tasks()
        return res.message

    def _build_state(self) -> str:
        """Собирает блок текущего состояния интерфейсов/агента."""
        return f"""
### [AGENT]
* Status: {self.agent_state.state.value}
* LLM Model: {self.agent_state.llm_model}
* Temperature: {self.agent_state.temperature}
* Uptime: {self.agent_state.get_uptime()}
* ReAct Step: {self.agent_state.current_step}/{self.agent_state.max_react_steps} (при превышении лимита - ReAct-цикл принудительно завершается)

### [HOST OS]
* Datetime: {self.host_os_state.datetime}
* Uptime: {self.host_os_state.uptime}
* Network: {getattr(self.host_os_state, 'network', 'Неизвестно')}
{self.host_os_state.telemetry}

### [HOST TERMINAL]
{self.terminal_state.messages}

### [TELETHON]
{self.telethon_state.last_chats}

### [AIOGRAM]
{self.aiogram_state.last_chats}
        """.strip()

    async def _build_recent_ticks(self, limit: int) -> str:
        """Собирает блок последних тиков агента."""
        ticks = await self.sql_ticks.get_ticks(limit=limit)

        if not ticks:
            return "Нет предыдущих тиков."

        blocks = []
        for i, t in enumerate(ticks, 1):

            # Превращаем массив действий в читаемую строку: func_name({"param": "val"})
            actions_list = [
                f"{a.get('tool_name')}({json.dumps(a.get('parameters', {}), ensure_ascii=False)})"
                for a in t.actions
            ]
            actions_str = ", ".join(actions_list) if actions_list else "None"

            res_str = json.dumps(t.results, ensure_ascii=False) if t.results else "None"

            blocks.append(
                f"#### [Tick {i}]\n"
                f"*Thoughts*: {t.thoughts}\n"
                f"*Actions*: {actions_str}\n"
                f"*Result*: {res_str}"
            )

        return "\n\n".join(blocks)

    def _build_wake_up_reason(self, event_name: str, payload: Dict[str, Any]) -> str:
        """Собирает причины пробуждения агента."""

        # Разбираем полезную нагрузку (кто написал, какой текст и т.д.)
        payload_lines = [f"{k}: {v}" for k, v in payload.items()]
        payload_str = (
            "\n".join(payload_lines) if payload_lines else "Нет дополнительных данных"
        )

        return f"EVENT - {event_name}\n{payload_str}"

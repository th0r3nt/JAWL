import json
import asyncio
from typing import TYPE_CHECKING, Any, Dict

from src.l3_agent.skills.registry import get_skills_library

if TYPE_CHECKING:
    from src.utils.settings import ContextDepthConfig, InterfacesConfig

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
        depth_config: "ContextDepthConfig",
        interfaces_config: "InterfacesConfig",
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

        # Конфиг
        self.depth_config = depth_config
        self.interfaces_config = interfaces_config

    async def build(
        self, event_name: str, payload: Dict[str, Any], missed_events: list[str]
    ) -> str:
        """Собирает готовый контекст для агента."""

        # Собираем данные из БД параллельно для ускорения работы
        traits_task = self._build_personality_traits()
        tasks_task = self._build_tasks()
        ticks_task = self._build_recent_ticks(limit=self.depth_config.ticks)

        personality_traits, tasks, recent_ticks = await asyncio.gather(
            traits_task, tasks_task, ticks_task
        )

        skills = self._build_skills()
        state = self._build_state()
        wake_up_reason = self._build_wake_up_reason(event_name, payload, missed_events)

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

        # Читаем реальное состояние, а не конфиг
        os_status = "ON" if self.host_os_state.is_online else "OFF"
        tel_status = "ON" if self.telethon_state.is_online else "OFF"
        aio_status = "ON" if self.aiogram_state.is_online else "OFF"

        # Для терминала даем агенту понять точную картину
        if self.terminal_state.is_online:
            term_status = "ON" if self.terminal_state.is_ui_connected else "WAITING_FOR_UI"
        else:
            term_status = "OFF"

        # Форматируем данные (если выключено - прячем мусор)
        os_data = self.host_os_state.telemetry if os_status == "ON" else "Интерфейс отключен."
        sandbox_data = self.host_os_state.sandbox_files if os_status == "ON" else ""
        term_data = (
            self.terminal_state.messages
            if term_status == "ON"
            else "Интерфейс отключен/ожидает подключения."
        )
        tel_data = (
            self.telethon_state.last_chats
            if tel_status == "ON"
            else "Интерфейс отключен (нет ключей или выключен)."
        )
        aio_data = (
            self.aiogram_state.last_chats
            if aio_status == "ON"
            else "Интерфейс отключен (нет ключей или выключен)."
        )

        return f"""
### AGENT
* LLM Model: {self.agent_state.llm_model}
* Temperature: {self.agent_state.temperature}
* Uptime: {self.agent_state.get_uptime()}
* ReAct Step: {self.agent_state.current_step}/{self.agent_state.max_react_steps}

### HOST OS [{os_status}]
* Datetime: {self.host_os_state.datetime}
* Uptime: {self.host_os_state.uptime}
* Network: {getattr(self.host_os_state, 'network', 'Неизвестно')}
{os_data}

* Sandbox Directory:
{sandbox_data}

### [HOST TERMINAL] [{term_status}]
{term_data}

### [TELETHON] [{tel_status}]
{tel_data}

### [AIOGRAM] [{aio_status}]
{aio_data}
        """.strip()

    async def _build_recent_ticks(self, limit: int) -> str:
        """Собирает блок последних тиков агента."""
        ticks = await self.sql_ticks.get_ticks(limit=limit)

        if not ticks:
            return "Нет предыдущих тиков."

        blocks = []
        max_chars = self.depth_config.tick_result_max_chars

        for i, t in enumerate(ticks, 1):

            # Форматируем действия в красивые inline-code блоки: `tool_name`({"param": "val"})
            actions_list = [
                f"`{a.get('tool_name')}`({json.dumps(a.get('parameters', {}), ensure_ascii=False)})"
                for a in t.actions
            ]
            actions_str = ", ".join(actions_list) if actions_list else "None"

            # Достаем сырую строку из execution_report (без экранирования \n от json.dumps)
            if t.results and "execution_report" in t.results:
                res_str = str(t.results["execution_report"])
            elif t.results:
                res_str = json.dumps(t.results, ensure_ascii=False)
            else:
                res_str = "None"

            # Обрезаем результат для сохранения контекста
            if len(res_str) > max_chars:
                res_str = (
                    res_str[:max_chars]
                    + f"\n... [Результат обрезан. Превышен лимит в {max_chars} символов]"
                )

            # Собираем красивый Markdown-блок для тика
            blocks.append(
                f"#### [Tick {i}]\n"
                f"*Thoughts*: {t.thoughts}\n"
                f"*Actions*: {actions_str}\n"
                f"*Result*:\n```\n{res_str}\n```"
            )

        return "\n\n".join(blocks)

    def _build_wake_up_reason(
        self, event_name: str, payload: Dict[str, Any], missed_events: list[str]
    ) -> str:
        """Собирает причины пробуждения агента и лог событий во время сна."""

        payload_lines = [f"{k}: {v}" for k, v in payload.items()]
        payload_str = (
            "\n".join(payload_lines) if payload_lines else "Нет дополнительных данных"
        )

        main_trigger = f"{event_name}\n{payload_str}"

        # Если были события, добавляем их списком
        if missed_events:
            events_log = "\n".join(missed_events)
            return f"{main_trigger}\n\nEvent Log:\n{events_log}"

        return main_trigger

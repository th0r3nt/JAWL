import json
import asyncio
import re
from datetime import timezone, timedelta
from typing import TYPE_CHECKING, Any, Dict

from src.l3_agent.skills.registry import get_skills_library, _REGISTRY

if TYPE_CHECKING:
    # yaml
    from src.utils.settings import ContextDepthConfig, InterfacesConfig, VectorDBConfig

    # States
    from src.l0_state.interfaces.state import (
        HostOSState,
        TelethonState,
        AiogramState,
        HostTerminalState,
        WebState,
    )
    from src.l0_state.agent.state import AgentState

    # SQL
    from src.l1_databases.sql.management.ticks import SQLTicks
    from src.l1_databases.sql.management.tasks import SQLTasks
    from src.l1_databases.sql.management.personality_traits import SQLPersonalityTraits
    from src.l1_databases.sql.management.mental_states import SQLMentalStates

    # Vector
    from src.l1_databases.vector.management.knowledge import VectorKnowledge
    from src.l1_databases.vector.management.thoughts import VectorThoughts


class ContextBuilder:
    """
    Отвечает за сборку динамического контекста для каждого вызова к LLM.
    """

    def __init__(
        self,
        # States
        host_os_state: "HostOSState",
        telethon_state: "TelethonState",
        aiogram_state: "AiogramState",
        terminal_state: "HostTerminalState",
        web_state: "WebState",
        agent_state: "AgentState",
        # SQL
        sql_ticks: "SQLTicks",
        sql_tasks: "SQLTasks",
        sql_traits: "SQLPersonalityTraits",
        sql_mental_states: "SQLMentalStates",
        # Vector
        vector_knowledge: "VectorKnowledge",
        vector_thoughts: "VectorThoughts",
        vector_db_config: "VectorDBConfig",
        # yaml
        depth_config: "ContextDepthConfig",
        interfaces_config: "InterfacesConfig",
        timezone: int,
    ):
        # States
        self.host_os_state = host_os_state
        self.telethon_state = telethon_state
        self.aiogram_state = aiogram_state
        self.terminal_state = terminal_state
        self.agent_state = agent_state
        self.web_state = web_state

        # SQL
        self.sql_ticks = sql_ticks
        self.sql_tasks = sql_tasks
        self.sql_traits = sql_traits
        self.sql_mental_states = sql_mental_states

        # Vector
        self.vector_knowledge = vector_knowledge
        self.vector_thoughts = vector_thoughts
        self.vector_db_config = vector_db_config

        # yaml
        self.depth_config = depth_config
        self.interfaces_config = interfaces_config
        self.timezone = timezone

    async def build(
        self, event_name: str, payload: Dict[str, Any], missed_events: list[str]
    ) -> str:
        """Собирает готовый контекст для агента."""

        # Асинхронные таски для сбора
        traits_task = self._build_personality_traits()
        mental_states_task = self._build_mental_states()
        tasks_task = self._build_tasks()
        ticks_task = self._build_recent_ticks(limit=self.depth_config.ticks)
        chat_histories_task = self._build_chat_histories(missed_events)
        rag_task = self._build_rag_memories(payload, missed_events)

        # Выполняем
        personality_traits, mental_states, tasks, recent_ticks, chat_histories, rag_memories = (
            await asyncio.gather(
                traits_task, mental_states_task, tasks_task, ticks_task, chat_histories_task, rag_task
            )
        )

        skills = self._build_skills()
        state = self._build_state()
        wake_up_reason = self._build_wake_up_reason(event_name, payload, missed_events)

        # Собираем блоки промпта
        context_blocks = [
            f"## PERSONALITY TRAITS \n{personality_traits}",
            f"## SKILLS \n{skills}",
            f"## TASKS \n{tasks}",
            f"## MENTAL STATES \nMax number of stored entities: {self.sql_mental_states.max_entities} \n{mental_states}",
            f"## STATE \n{state}",
        ]

        # Внедряем динамически добытую инфу
        if chat_histories:
            context_blocks.append(f"## SPECIFIC CHAT HISTORY\n{chat_histories}")

        if rag_memories:
            context_blocks.append(f"## RELEVANT INFORMATION (Автоматический RAG)\n{rag_memories}")

        context_blocks.extend(
            [
                f"## RECENT TICKS \n{recent_ticks}",
                f"## HEARTBEAT \n{wake_up_reason}",
            ]
        )

        return "\n\n".join(context_blocks).strip()

    # ===================================================
    # СБОРКА КОНТЕКСТА
    # ===================================================

    async def _build_rag_memories(
        self, payload: Dict[str, Any], missed_events: list[str]
    ) -> str:
        """
        Умная эвристика векторного поиска:
        извлекает имена, длинные сообщения и названия непрочитанных чатов,
        а затем ищет совпадения в Knowledge и Thoughts.
        """

        queries = set()

        # Из Payload (Имя отправителя и суть сообщения)
        sender = payload.get("sender_name")
        if sender and sender.lower() != "unknown":
            queries.add(sender.strip())

        msg = payload.get("message", "")
        # Анти-мусор: ищем только если сообщение осмысленное (>10 симв или >2 слов)
        if len(msg) > 10 or len(msg.split()) > 2:
            queries.add(msg.strip())

        # Из логов пропущенных событий (пока агент спал)
        for event in missed_events:
            match_sender = re.search(r"sender_name=([^,]+)", event)
            if match_sender and match_sender.group(1).lower() != "unknown":
                queries.add(match_sender.group(1).strip())

            match_msg = re.search(r"message=([^,]+)", event)
            if match_msg:
                text = match_msg.group(1).strip()
                if len(text) > 15 or len(text.split()) > 3:
                    queries.add(text)

        # Из названий чатов с непрочитанными сообщениями
        for line in self.telethon_state.last_chats.split("\n"):
            if "[Непрочитанных:" in line:
                match_name = re.search(r"Название:\s*(.+?)\s*\[", line)
                if match_name:
                    queries.add(match_name.group(1).strip())

        if not queries:
            return ""

        # Чтобы не DdoS'ить собственную базу, берем максимум 10 запросов
        queries = list(queries)[:10]
        limit = self.vector_db_config.auto_rag_top_k

        # Параллельный поиск по Knowledge и Thoughts для каждого запроса
        tasks = []
        for q in queries:
            tasks.append(self.vector_knowledge.search_knowledge(query=q, limit=limit))
            tasks.append(self.vector_thoughts.search_thoughts(query=q, limit=limit))

        results = await asyncio.gather(*tasks)

        memory_blocks = []
        for i, res in enumerate(results):
            # Пропускаем ошибки и пустые результаты (в скиллах они возвращают "не дал результатов" или "пуста")
            if (
                res.is_success
                and "не дал результатов" not in res.message
                and "пуста" not in res.message
            ):
                # Каждые 2 таски относятся к одному запросу (0,1 -> query[0]; 2,3 -> query[1] и т.д.)
                q = queries[i // 2]
                source = "Knowledge" if i % 2 == 0 else "Thoughts"

                memory_blocks.append(f"### Найдено по ключу '{q}' ({source}):\n{res.message}")

        return "\n\n".join(memory_blocks)

    async def _build_chat_histories(self, missed_events: list[str]) -> str:
        """
        Динамически подтягивает историю диалогов, если были новые сообщения в логах
        или есть непрочитанные в State.
        """

        chat_ids = set()

        for event in missed_events:
            match = re.search(r"chat_id=(-?\d+)", event)
            if match:
                chat_ids.add(int(match.group(1)))

        for line in self.telethon_state.last_chats.split("\n"):
            if "[Непрочитанных:" in line:
                match = re.search(r"ID:\s*(-?\d+)", line)
                if match:
                    chat_ids.add(int(match.group(1)))

        if not chat_ids:
            return ""

        read_chat_func = _REGISTRY.get("TelethonChats.read_chat")
        if not read_chat_func:
            return ""

        history_blocks = []
        for chat_id in chat_ids:
            try:
                res = await read_chat_func(chat_id=chat_id, limit=15)
                if res.is_success:
                    history_blocks.append(f"### История чата ID: {chat_id}\n{res.message}")
            except Exception:
                pass

        return "\n\n".join(history_blocks)

    async def _build_personality_traits(self) -> str:
        res = await self.sql_traits.get_traits()
        return res.message

    def _build_skills(self) -> str:
        return get_skills_library()

    async def _build_tasks(self) -> str:
        res = await self.sql_tasks.get_tasks()
        return res.message

    def _build_state(self) -> str:
        os_status = "ON" if self.host_os_state.is_online else "OFF"
        tel_status = "ON" if self.telethon_state.is_online else "OFF"
        aio_status = "ON" if self.aiogram_state.is_online else "OFF"
        web_status = "ON" if self.web_state.is_online else "OFF"

        os_data = self.host_os_state.telemetry if os_status == "ON" else "Интерфейс отключен."
        sandbox_data = self.host_os_state.sandbox_files if os_status == "ON" else ""

        tel_data = (
            self.telethon_state.last_chats if tel_status == "ON" else "Интерфейс отключен."
        )
        aio_data = (
            self.aiogram_state.last_chats if aio_status == "ON" else "Интерфейс отключен."
        )
        web_data = (
            self.web_state.browser_history if web_status == "ON" else "Интерфейс отключен."
        )

        madness_map = {0: "CAGE", 1: "VOYEUR", 2: "SURGEON", 3: "GOD_MODE"}
        ml_val = self.interfaces_config.host.os.madness_level
        madness_str = f"{ml_val} ({madness_map.get(ml_val, 'UNKNOWN')}) / 3"

        return f"""
### AGENT
* LLM Model: {self.agent_state.llm_model}
* Temperature: {self.agent_state.temperature}
* Uptime: {self.agent_state.get_uptime()}
* ReAct Step: {self.agent_state.current_step}/{self.agent_state.max_react_steps}

### HOST OS [{os_status}]
* Madness Level (Access Level): {madness_str}
* Datetime: {self.host_os_state.datetime}
* Uptime: {self.host_os_state.uptime}
* Network: {getattr(self.host_os_state, 'network', 'Неизвестно')}
{os_data}

* Sandbox Directory:
{sandbox_data}

### TELETHON [{tel_status}]
{tel_data}

### AIOGRAM [{aio_status}]
{aio_data}

### WEB [{web_status}]
{web_data}
        """.strip()

    async def _build_recent_ticks(self, limit: int) -> str:
        ticks = await self.sql_ticks.get_ticks(limit=limit)

        if not ticks:
            return "Нет предыдущих тиков."

        blocks = []
        history_max_chars = 500

        for t in ticks:
            actions_list = [
                f"`{a.get('tool_name')}`({json.dumps(a.get('parameters', {}), ensure_ascii=False)})"
                for a in t.actions
            ]
            actions_str = ", ".join(actions_list) if actions_list else "None"

            if t.results and "execution_report" in t.results:
                res_str = str(t.results["execution_report"])
            elif t.results:
                res_str = json.dumps(t.results, ensure_ascii=False, indent=2)
            else:
                res_str = "None"

            if len(res_str) > history_max_chars:
                res_str = (
                    res_str[:history_max_chars]
                    + f"\n... [Результат обрезан. Превышен лимит истории в {history_max_chars} символов]"
                )

            if hasattr(t.created_at, "strftime"):
                dt = t.created_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                tz = timezone(timedelta(hours=self.timezone))
                time_str = dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = str(t.created_at)[:19]

            short_id = t.id[:8]

            blocks.append(
                f"#### [Tick ID: {short_id}] ({time_str})\n"
                f"*Thoughts*: {t.thoughts}\n"
                f"*Actions*: {actions_str}\n"
                f"*Result*:\n```\n{res_str}\n```"
            )

        return "\n\n".join(blocks)

    def _build_wake_up_reason(
        self, event_name: str, payload: Dict[str, Any], missed_events: list[str]
    ) -> str:
        payload_lines = [f"{k}: {v}" for k, v in payload.items()]
        payload_str = (
            "\n".join(payload_lines) if payload_lines else "Нет дополнительных данных"
        )

        main_trigger = f"{event_name}\n{payload_str}"

        if missed_events:
            events_log = "\n".join(missed_events)
            return f"{main_trigger}\n\nEvent Log:\n{events_log}"

        return main_trigger

    async def _build_mental_states(self) -> str:
            res = await self.sql_mental_states.get_mental_states()
            return res.message
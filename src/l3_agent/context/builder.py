from typing import Any, Dict, List
from src.l0_state.agent.state import AgentState
from src.l3_agent.context.registry import ContextRegistry
from src.l3_agent.skills.registry import get_skills_library


class ContextBuilder:
    """
    Сборщик контекста. Берет данные из реестра и выстраивает их в строгой иерархии
    для оптимальной работы механизма внимания LLM.
    """

    def __init__(
        self,
        agent_state: AgentState,
        registry: ContextRegistry,
    ):
        self.agent_state = agent_state
        self.registry = registry

    async def build(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[str]
    ) -> str:
        """Собирает итоговый контекст для агента в строгом порядке."""

        blocks = await self.registry.gather_all(
            event_name=event_name, payload=payload, missed_events=missed_events
        )

        ordered_parts = []

        # Строгий порядок блоков контейста

        # ## PERSONALITY TRAITS
        if "sql_traits" in blocks:
            ordered_parts.append(blocks["sql_traits"])

        # ## SKILLS
        ordered_parts.append(f"## SKILLS\n{get_skills_library()}")

        # ## INTERFACES
        # Указываем порядок вывода интерфейсов друг за другом
        interface_keys = [
            "agent_state",
            "host os",
            "meta",
            "telethon",
            "aiogram",
            "web search",
        ]
        interfaces = [blocks[k] for k in interface_keys if k in blocks and blocks[k]]

        if interfaces:
            ordered_parts.append("\n\n".join(interfaces))

        # ## MENTAL STATES
        if "sql_mental_states" in blocks:
            ordered_parts.append(blocks["sql_mental_states"])

        # ## TASKS
        if "sql_tasks" in blocks:
            ordered_parts.append(blocks["sql_tasks"])

        # ## RAG MEMORIES
        if "rag memories" in blocks:
            ordered_parts.append(blocks["rag memories"])

        # ## RECENT TICKS
        if "sql_ticks" in blocks:
            ordered_parts.append(blocks["sql_ticks"])

        # ## HEARTBEAT & EVENT LOGS (Причина пробуждения - всегда в самом низу)
        wake_up_reason = self._build_wake_up_reason(event_name, payload, missed_events)
        ordered_parts.append(f"## HEARTBEAT\n{wake_up_reason}")

        # Склеиваем с мощным отступом для чистоты Markdown
        return "\n\n\n\n\n".join(ordered_parts).strip()

    def _build_wake_up_reason(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[str]
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

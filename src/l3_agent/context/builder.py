from typing import Any, Dict, List
from src.l0_state.agent.state import AgentState
from src.l3_agent.context.registry import ContextRegistry
from src.l3_agent.skills.registry import get_skills_library


class ContextBuilder:
    """
    Тонкий сборщик контекста.
    Делегирует сбор данных зарегистрированным провайдерам (ContextRegistry).
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
        """Собирает итоговый контекст для агента."""

        # Сборка статических блоков самого агента
        skills = get_skills_library()
        wake_up_reason = self._build_wake_up_reason(event_name, payload, missed_events)

        # Динамический опрос всех интерфейсов, баз данных и RAG информации
        dynamic_context = await self.registry.gather_all(
            event_name=event_name, payload=payload, missed_events=missed_events
        )

        # Склеиваем всё воедино
        context_blocks = [
            f"## SKILLS \n{skills}",
            dynamic_context,  # Тут лежат инфа с баз данных, интерфейсов и RAG
            f"## HEARTBEAT \n{wake_up_reason}",
        ]

        return "\n\n".join(context_blocks).strip()

    # TODO: не нравится, что эта функция тут, нужно перенести куда-нибудь
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

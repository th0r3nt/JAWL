from typing import Any, Dict, List
from src.l0_state.agent.state import AgentState
from src.l3_agent.context.registry import ContextRegistry, ContextSection
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

        # Регистрируем встроенные провайдеры напрямую (с нужным приоритетом)
        self.registry.register_provider(
            "skills", self._skills_provider, section=ContextSection.SKILLS
        )
        self.registry.register_provider(
            "heartbeat", self._heartbeat_provider, section=ContextSection.HEARTBEAT
        )

    async def build(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[str]
    ) -> str:
        """Собирает итоговый контекст для агента в строгом порядке."""

        blocks = await self.registry.gather_all(
            event_name=event_name,
            payload=payload,
            missed_events=missed_events,
            agent_state=self.agent_state,
        )

        # blocks уже отсортированы по приоритетам
        # Просто склеиваем их с мощным отступом для чистоты Markdown
        return "\n\n\n\n\n".join(blocks.values()).strip()

    # =================================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # =================================================================

    async def _skills_provider(self, **kwargs) -> str:
        """Возвращает отформатированный блок контекста доступных скиллов для агента."""

        return f"## SKILLS\n{get_skills_library()}"

    async def _heartbeat_provider(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[str], **kwargs
    ) -> str:
        """Возвращает отформатированный блок контекста текущего Heartbeat для агента."""

        wake_up_reason = self._build_wake_up_reason(event_name, payload, missed_events)
        return f"## HEARTBEAT\n{wake_up_reason}"

    def _build_wake_up_reason(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[str]
    ) -> str:
        """Возвращает отформатированный блок контекста фоновых событий для агента."""

        payload_lines = [f"{k}: {v}" for k, v in payload.items()]
        payload_str = (
            "\n".join(payload_lines) if payload_lines else "Нет дополнительных данных"
        )

        main_trigger = f"{event_name}\n{payload_str}"

        if missed_events:
            events_log = "\n".join(missed_events)
            return f"{main_trigger}\n\nEvent Log:\n{events_log}"

        return main_trigger

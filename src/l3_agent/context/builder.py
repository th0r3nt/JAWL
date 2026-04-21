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
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
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
        self,
        event_name: str,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        **kwargs,
    ) -> str:
        """Возвращает отформатированный блок контекста текущего Heartbeat."""

        # 1. Форматируем текущий триггер (то, почему мы проснулись прямо сейчас)
        current_trigger = self._format_single_event(event_name, payload)

        # 2. Форматируем список пропущенных событий (Event Log)
        log_blocks = []
        for evt in missed_events:
            # evt теперь словарь из heartbeat.py
            formatted = self._format_single_event(
                event_name=evt["name"],
                payload=evt["payload"],
                event_time=evt["time"],
                level=evt["level"],
            )
            log_blocks.append(formatted)

        event_log = "\n\n---\n\n".join(log_blocks) if log_blocks else "No other events in log"

        return f"""
## HEARTBEAT
### CURRENT TRIGGER
{current_trigger}

### EVENT LOG (missed while sleeping or thinking)
{event_log}
""".strip()

    def _build_answer_to_event_reason(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
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

    def _format_single_event(
        self,
        event_name: str,
        payload: Dict[str, Any],
        event_time: str = None,
        level: str = None,
    ) -> str:
        """Вспомогательный метод для красивого Markdown-оформления события."""

        header = f"**{event_name}**"
        if event_time and level:
            header = f"[{event_time}] [{level}] {header}"

        # Выделяем важные поля, остальное в список
        msg = payload.get("message", "No message content")
        sender = payload.get("sender_name", "Unknown")
        history = payload.get("recent_history", "")

        # Собираем доп. поля (chat_id, msg_id и т.д.), исключая уже обработанные
        other_meta = [
            f"* {k}: {v}"
            for k, v in payload.items()
            if k not in ["message", "sender_name", "recent_history"]
        ]
        meta_str = "\n".join(other_meta)

        block = f"{header}\nSender: {sender}\nMessage: {msg}"
        if meta_str:
            block += f"\n{meta_str}"
        if history:
            block += f"\n\n#### Recent Chat History:\n{history}"

        return block

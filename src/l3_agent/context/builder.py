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
        return "\n\n\n".join(blocks.values()).strip()

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
        """
        Возвращает отформатированный блок контекста текущего Heartbeat.
        """

        local_event_name = event_name
        local_payload = payload.copy()
        local_missed_events = missed_events.copy()

        # На шагах > 1 прячем оригинальный триггер в лог, а текущим ставим HEARTBEAT
        if self.agent_state.current_step > 1 and local_event_name != "HEARTBEAT":
            processed_event = {
                "name": f"{local_event_name} [Уже получено на 1-м шаге]",
                "payload": local_payload.copy(),
                "time": "Step 1",
                "level": "PROCESSED",
            }
            local_missed_events.append(processed_event)

            # Подменяем текущий триггер
            local_event_name = "HEARTBEAT"
            local_payload = {}

        seen_chat_histories = set()

        # Форматируем текущий триггер (он самый свежий)
        if local_payload.get("chat_id") and "recent_history" in local_payload:
            seen_chat_histories.add(local_payload["chat_id"])

        current_trigger = self._format_single_event(local_event_name, local_payload)

        # Форматируем список пропущенных событий (Event Log)
        log_blocks = []

        # Идем с конца (от самых свежих к старым), чтобы оставить историю только у самого последнего
        for evt in reversed(local_missed_events):
            evt_payload = evt["payload"].copy()
            chat_id = evt_payload.get("chat_id")

            if chat_id and "recent_history" in evt_payload:
                if chat_id in seen_chat_histories:
                    # История этого чата уже есть в более свежем событии, удаляем дубликат
                    del evt_payload["recent_history"]
                else:
                    seen_chat_histories.add(chat_id)

            formatted = self._format_single_event(
                event_name=evt["name"],
                payload=evt_payload,
                event_time=evt.get("time"),
                level=evt.get("level"),
            )
            # Вставляем в начало, чтобы вернуть хронологический порядок (старые сверху)
            log_blocks.insert(0, formatted)

        event_log = "\n\n---\n\n".join(log_blocks) if log_blocks else "No other events in log"

        # Сначала лог, потом системный триггер
        return f"""
## EVENT LOG (missed while sleeping or thinking)
{event_log}

---

## CURRENT TRIGGER
{current_trigger}
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

        proactive_prompt = """
[SYSTEM]
Рекомендуется проактивное выполнение действий.

Векторы активности могут включать: 
- Выполнение шагов по долгосрочным задачам.
- Сбор данных во внешних сетях по релевантным тематикам.
- Ревизия, консолидация или удаление ненужных данных в подсистемах памяти.
- Рефлексия о недавних действиях.
- Очистка рабочих директорий от нерелевантных файлов.
- Составление/создание новых задач для выполнения.

В случае, если текущих задач нет - системе рекомендуется проактивно поставить их (Tasks).
"""

        header = f"**{event_name}**"
        if event_time and level:
            header = f"[{event_time}] [{level}] {header}"

        if event_name == "HEARTBEAT":
            if self.agent_state.proactive_guidance:
                return f"{header}\n[Статус: Heartbeat тик] \n{proactive_prompt}"
            else:
                return f"{header}\n[Статус: Heartbeat тик]"

        if event_name == "SYSTEM_CORE_START":
            return f"{header}\n[Статус: Инициализация ядра JAWL. Запуск подсистем завершен]"

        if event_name == "SYSTEM_CALENDAR_ALARM":
            alarm_title = payload.get("title", "Неизвестно")
            return f"{header}\n[Статус: Срабатывание системного таймера]\n\nЗадача: {alarm_title}."

        lines = [header]

        if "sender_name" in payload:
            lines.append(f"Sender: {payload['sender_name']}")

        if "message" in payload:
            lines.append(f"Message: {payload['message']}")

        for k, v in payload.items():
            if k not in ["message", "sender_name", "recent_history"]:
                lines.append(f"* {k}: {v}")

        if "recent_history" in payload and payload["recent_history"]:
            lines.append(f"\n#### Recent Chat History:\n{payload['recent_history']}")

        return "\n".join(lines)

"""
Module for Dynamic Context Assembly (User Prompt).

Gathers snapshots and caching buffers from all active L0 States and L2 interfaces
and merges them in a strict hierarchical order. Ensures optimal performance of the
LLM attention mechanism by placing critical information closer to attention horizons.
"""

from typing import Any, Dict, List

from src.l0_state.agent.state import AgentState
from src.utils.settings import SubconsciousConfig

from src.l3_agent.context.registry import ContextRegistry, ContextSection
from src.l3_agent.skills.registry import get_skills_library


class ContextBuilder:
    """
    Context assembler. Retrieves data from the registry and structures
    the blocks in a strict hierarchy for optimal LLM attention allocation.
    """

    def __init__(
        self,
        agent_state: AgentState,
        registry: ContextRegistry,
        subconscious_config: SubconsciousConfig = None,
    ) -> None:
        """
        Initializes the builder and automatically registers mandatory system providers.

        Args:
            agent_state: Agent L0 State instance.
            registry: Global context providers registry.
        """
        self.agent_state = agent_state
        self.registry = registry
        self.subconscious_config = subconscious_config

        self.registry.register_provider(
            "skills", self._skills_provider, section=ContextSection.SKILLS
        )
        self.registry.register_provider(
            "heartbeat", self._heartbeat_provider, section=ContextSection.HEARTBEAT
        )
        self.registry.register_provider(
            "tree_of_thoughts", self._tot_provider, section=ContextSection.TREE_OF_THOUGHTS
        )

    async def build(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
    ) -> str:
        """
        Compiles the final context (User Message) for the agent in a strict order.

        Args:
            event_name: Name of the primary trigger event that woke up the agent.
            payload: Parameters and metadata of the primary trigger.
            missed_events: List of background events missed while sleeping.

        Returns:
            str: Compiled and formatted Markdown context block for the LLM.
        """

        blocks = await self.registry.gather_all(
            event_name=event_name,
            payload=payload,
            missed_events=missed_events,
            agent_state=self.agent_state,
        )

        return "\n\n\n".join(blocks.values()).strip()

    # -------------------------------------------------------------------------
    # Service Providers
    # -------------------------------------------------------------------------

    async def _skills_provider(self, **kwargs: Any) -> str:
        """
        Returns a formatted block describing currently available skills.
        """
        return f"## SKILLS\n{get_skills_library(self.subconscious_config)}"

    async def _heartbeat_provider(
        self,
        event_name: str,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        """
        Returns the primary trigger (Heartbeat/Wakeup) block.
        Injects proactive guidelines if corresponding settings are enabled.
        """

        local_event_name = event_name
        local_payload = payload.copy()
        local_missed_events = missed_events.copy()

        # On steps > 1 hide the original trigger in history and set CURRENT to HEARTBEAT
        if self.agent_state.current_step > 1 and local_event_name != "HEARTBEAT":
            processed_event = {
                "name": f"{local_event_name} [Already received on step 1]",
                "payload": local_payload.copy(),
                "time": "Step 1",
                "level": "PROCESSED",
            }
            local_missed_events.append(processed_event)

            local_event_name = "HEARTBEAT"
            local_payload = {}

        seen_chat_histories = set()

        if local_payload.get("chat_id") and "recent_history" in local_payload:
            seen_chat_histories.add(local_payload["chat_id"])

        current_trigger = self._format_single_event(local_event_name, local_payload)

        # Format missed background events (Event Log)
        log_blocks = []

        # Walk backwards (from newest to oldest) to preserve history on the freshest event only
        for evt in reversed(local_missed_events):
            evt_payload = evt["payload"].copy()
            chat_id = evt_payload.get("chat_id")

            if chat_id and "recent_history" in evt_payload:
                if chat_id in seen_chat_histories:
                    del evt_payload["recent_history"]
                else:
                    seen_chat_histories.add(chat_id)

            formatted = self._format_single_event(
                event_name=evt["name"],
                payload=evt_payload,
                event_time=evt.get("time"),
                level=evt.get("level"),
            )
            log_blocks.insert(0, formatted)

        event_log = "\n\n---\n\n".join(log_blocks) if log_blocks else "No other events in log"

        return f"""
## EVENT LOG (missed while sleeping/thinking)
{event_log}

---

## CURRENT TRIGGER
{current_trigger}
""".strip()

    def _build_answer_to_event_reason(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
    ) -> str:
        """
        Utility method that returns a formatted text summary of background events.
        """

        payload_lines = [f"{k}: {v}" for k, v in payload.items()]
        payload_str = "\n".join(payload_lines) if payload_lines else "No data"

        main_trigger = f"{event_name}\n{payload_str}"

        if missed_events:
            events_log = "\n".join(str(e) for e in missed_events)
            return f"{main_trigger}\n\nEvent Log:\n{events_log}"

        return main_trigger

    def _format_single_event(
        self,
        event_name: str,
        payload: Dict[str, Any],
        event_time: str = None,
        level: str = None,
    ) -> str:
        """
        Helper method for clean Markdown formatting of a single event.

        Args:
            event_name: Event name.
            payload: Event payload dict.
            event_time: Optional time string.
            level: Event level name (CRITICAL, HIGH, etc.).

        Returns:
            str: Formatted Markdown block.
        """

        proactive_prompt = """
[SYSTEM]
Proactive action execution is recommended.

Activity vectors may include:

- Executing steps for long-term tasks.
- Gathering data in external networks on relevant topics.
- Revising, consolidating, or deleting unnecessary data in memory subsystems.
- Reflecting on recent actions.
- Clearing working directories of irrelevant files.
- Drafting/creating new tasks for execution.

In the absence of current tasks, the system is advised to proactively generate them.
"""

        header = f"**{event_name}**"
        if event_time and level:
            header = f"[{event_time}] [{level}] {header}"

        if event_name == "HEARTBEAT":
            if self.agent_state.proactive_guidance:
                return f"{header}\n[Status: Heartbeat tick] \n{proactive_prompt}"
            else:
                return f"{header}\n[Heartbeat tick]"

        if event_name == "SYSTEM_CORE_START":
            return f"{header}\n[Initializing JAWL kernel. Subsystem startup complete]"

        if event_name == "SYSTEM_CALENDAR_ALARM":
            alarm_title = payload.get("title", "Unknown")
            return f"{header}\n[System timer triggered]\n\nTask: {alarm_title}."

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

    async def _tot_provider(self, **kwargs: Any) -> str:
        """
        Injects the generated thoughts tree (if any).
        """

        if self.agent_state.current_thoughts_tree:
            return self.agent_state.current_thoughts_tree
        return ""

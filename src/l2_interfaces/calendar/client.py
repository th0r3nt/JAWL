"""
Client for managing system time and schedules (Calendar).

Manages serialization of timers (alarms) to JSON and provides the agent
in L0 State with a sorted list of upcoming events/wakeups.
"""

import json
from pathlib import Path
from typing import List, Dict, Any

from src.l2_interfaces.calendar.state import CalendarState
from src.utils.dtime import format_timestamp


class CalendarClient:
    """
    Calendar interface client.
    Manages saving/loading of the JSON events file and the context provider.
    """

    def __init__(
        self,
        state: CalendarState,
        data_dir: Path,
        timezone: int,
        upcoming_events_limit: int = 10,
    ) -> None:
        """
        Initializes the calendar client.

        Args:
            state: L0 state (calendar dashboard).
            data_dir: Local data root directory.
            timezone: Timezone offset.
            upcoming_events_limit: Maximum number of events to display in the system prompt.
        """
        self.state = state
        self.timezone = timezone
        self.upcoming_events_limit = upcoming_events_limit

        self.calendar_dir = data_dir / "interfaces" / "calendar"
        self.calendar_dir.mkdir(parents=True, exist_ok=True)
        self.filepath = self.calendar_dir / "events.json"

        if not self.filepath.exists():
            self._save([])
        else:
            self.update_state_view()  # Update state on startup from existing file

    def _load(self) -> List[Dict[str, Any]]:
        """Loads data from JSON calendar."""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, events: List[Dict[str, Any]]) -> None:
        """
        Saves data to the JSON calendar and IMMEDIATELY updates the agent's state.

        Args:
            events: List of dicts with timers.
        """
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=4, ensure_ascii=False)

        # Instant cache synchronization after any file change!
        self.update_state_view()

    def update_state_view(self) -> None:
        """
        Aggregates and sorts current timers, calculating upcoming triggers.
        Updates the agent's MRU-cache (L0 State), strictly truncating the list to `upcoming_events_limit`
        to avoid overflowing the system prompt with thousands of scheduled tasks.
        """
        events = self._load()
        if not events:
            self.state.upcoming_events = "There are no scheduled events."
            return

        # Sort by nearest trigger time and apply limit from config
        sorted_events = sorted(events, key=lambda x: x["trigger_at"])[
            : self.upcoming_events_limit
        ]

        lines = ["Upcoming events:"]
        for ev in sorted_events:
            dt_str = format_timestamp(ev["trigger_at"], self.timezone, "%m-%d %H:%M")
            ev_type = ev["type"].upper()
            lines.append(f"-[{dt_str}] [ID: `{ev['id'][:8]}`] ({ev_type}) {ev['title']}")

        self.state.upcoming_events = "\n".join(lines)

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Returns all events in the calendar."""
        return self._load()

    def add_event(self, event_data: Dict[str, Any]) -> None:
        """
        Adds a new event to the calendar.

        Args:
            event_data: Dict with timer data (id, type, title, trigger_at).
        """
        events = self._load()
        events.append(event_data)
        self._save(events)

    def update_events(self, events: List[Dict[str, Any]]) -> None:
        """Full list rewrite (used when deleting or changing time)."""
        self._save(events)

    async def get_context_block(self, **kwargs: Any) -> str:
        """Context provider for ContextRegistry."""
        desc = "Description: Time management and scheduled alarms/timers."
        if not self.state.is_online:
            return f"### CALENDAR [OFF] \n{desc}\nThe interface is disabled."

        return f"### CALENDAR [ON] \n{desc}\n{self.state.upcoming_events}"

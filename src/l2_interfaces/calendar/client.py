import json
from pathlib import Path
from typing import List, Dict, Any

from src.l0_state.interfaces.state import CalendarState


class CalendarClient:
    """
    Клиент интерфейса Календаря.
    Управляет JSON-файлом событий и провайдером контекста.
    """

    def __init__(self, state: CalendarState, data_dir: Path, timezone: int):
        self.state = state
        self.timezone = timezone

        self.calendar_dir = data_dir / "calendar"
        self.calendar_dir.mkdir(parents=True, exist_ok=True)
        self.filepath = self.calendar_dir / "events.json"

        if not self.filepath.exists():
            self._save([])

    def _load(self) -> List[Dict[str, Any]]:
        """Загружает данные из JSON-календаря."""

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, events: List[Dict[str, Any]]) -> None:
        """Сохраняет данные в JSON-календарь."""

        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=4, ensure_ascii=False)

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Возвращает все события в календаре."""
        return self._load()

    def add_event(self, event_data: Dict[str, Any]) -> None:
        """Добавляет новое событие в календарь."""

        events = self._load()
        events.append(event_data)
        self._save(events)

    def update_events(self, events: List[Dict[str, Any]]) -> None:
        """Полная перезапись списка (нужно при удалении или изменении времени срабатывания)."""
        self._save(events)

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        """

        if not self.state.is_online:
            return "### CALENDAR [OFF] \nИнтерфейс отключен."

        return f"### CALENDAR [ON] \n{self.state.upcoming_events}"

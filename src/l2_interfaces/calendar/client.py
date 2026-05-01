"""
Клиент управления системным временем и расписанием (Календарь).

Управляет сериализацией таймеров (будильников) в JSON и предоставляет агенту
в L0 State отсортированный список ближайших событий/пробуждений.
"""

import json
from pathlib import Path
from typing import List, Dict, Any

from src.l0_state.interfaces.calendar_state import CalendarState
from src.utils.dtime import format_timestamp


class CalendarClient:
    """
    Клиент интерфейса Календаря.
    Управляет сохранением/загрузкой JSON-файла событий и провайдером контекста.
    """

    def __init__(
        self,
        state: CalendarState,
        data_dir: Path,
        timezone: int,
        upcoming_events_limit: int = 10,
    ) -> None:
        """
        Инициализирует клиент календаря.

        Args:
            state: L0 стейт (приборная панель календаря).
            data_dir: Корневая директория локальных данных.
            timezone: Смещение часового пояса.
            upcoming_events_limit: Максимальное кол-во событий для отображения в системном промпте.
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
            self.update_state_view()  # Обновляем стейт при старте из существующего файла

    def _load(self) -> List[Dict[str, Any]]:
        """Загружает данные из JSON-календаря."""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, events: List[Dict[str, Any]]) -> None:
        """
        Сохраняет данные в JSON-календарь и МГНОВЕННО обновляет стейт агента.

        Args:
            events: Список словарей с таймерами.
        """
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=4, ensure_ascii=False)

        # Мгновенная синхронизация кэша после любого изменения файла!
        self.update_state_view()

    def update_state_view(self) -> None:
        """
        Агрегирует и сортирует текущие таймеры, вычисляя ближайшие срабатывания.
        Обновляет MRU-кэш (L0 State) агента, жестко обрезая список до `upcoming_events_limit`,
        чтобы не переполнять системный промпт при тысячах запланированных задач.
        """
        events = self._load()
        if not events:
            self.state.upcoming_events = "Запланированных событий нет."
            return

        # Сортируем по ближайшему времени срабатывания и применяем лимит из конфига
        sorted_events = sorted(events, key=lambda x: x["trigger_at"])[
            : self.upcoming_events_limit
        ]

        lines = ["Ближайшие события:"]
        for ev in sorted_events:
            dt_str = format_timestamp(ev["trigger_at"], self.timezone, "%m-%d %H:%M")
            ev_type = ev["type"].upper()
            lines.append(f"-[{dt_str}] [ID: `{ev['id'][:8]}`] ({ev_type}) {ev['title']}")

        self.state.upcoming_events = "\n".join(lines)

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Возвращает все события в календаре."""
        return self._load()

    def add_event(self, event_data: Dict[str, Any]) -> None:
        """
        Добавляет новое событие в календарь.

        Args:
            event_data: Словарь с данными таймера (id, type, title, trigger_at).
        """
        events = self._load()
        events.append(event_data)
        self._save(events)

    def update_events(self, events: List[Dict[str, Any]]) -> None:
        """Полная перезапись списка (используется при удалении или изменении времени)."""
        self._save(events)

    async def get_context_block(self, **kwargs: Any) -> str:
        """Провайдер контекста для ContextRegistry."""
        if not self.state.is_online:
            return "### CALENDAR [OFF] \nИнтерфейс отключен."

        return f"### CALENDAR [ON] \n{self.state.upcoming_events}"

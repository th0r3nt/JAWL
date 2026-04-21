import time
import asyncio

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.dtime import format_timestamp

from src.l0_state.interfaces.state import CalendarState
from src.l2_interfaces.calendar.client import CalendarClient


class CalendarEvents:
    """
    Фоновый поллинг событий календаря.
    Сравнивает текущее время с trigger_at. Если сработало — будит агента.
    """

    def __init__(
        self,
        client: CalendarClient,
        state: CalendarState,
        event_bus: EventBus,
        polling_interval: int,
    ):
        self.client = client
        self.state = state
        self.bus = event_bus
        self.polling_interval = polling_interval

        self._is_running = False
        self._polling_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Запускает фоновый поллинг событий календаря."""

        if self._is_running:
            return

        self._is_running = True
        self.client.state.is_online = True
        self._update_state_view()

        self._polling_task = asyncio.create_task(self._loop())
        system_logger.info("[Calendar] Фоновый мониторинг времени запущен.")

    async def stop(self) -> None:
        """Останавливает фоновый поллинг событий календаря."""

        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None

        self.client.state.is_online = False
        system_logger.info("[Calendar] Фоновый мониторинг времени остановлен.")

    def _update_state_view(self):
        """Обновляет MRU-кэш для CalendarState (ближайшие 5 событий)."""

        events = self.client.get_all_events()
        if not events:
            self.state.upcoming_events = "Запланированных событий нет."
            return

        # Сортируем по ближайшему времени срабатывания
        sorted_events = sorted(events, key=lambda x: x["trigger_at"])[
            :10
        ]  # TODO: перенести в yaml

        lines = ["Ближайшие события:"]
        for ev in sorted_events:
            dt_str = format_timestamp(ev["trigger_at"], self.client.timezone, "%m-%d %H:%M")
            ev_type = ev["type"].upper()
            lines.append(f"- [{dt_str}] [ID: `{ev['id'][:6]}`] ({ev_type}) {ev['title']}")

        self.state.upcoming_events = "\n".join(lines)

    async def _loop(self):
        """Бесконечный цикл проверки таймеров."""

        while self._is_running:
            try:
                now = time.time()
                events = self.client.get_all_events()
                modified = False
                active_events = []

                for ev in events:
                    if now >= ev["trigger_at"]:
                        # Кидаем ивент агенту, будим
                        await self.bus.publish(
                            Events.SYSTEM_CALENDAR_ALARM,
                            alarm_id=ev["id"],
                            title=ev["title"],
                            type=ev["type"],
                        )
                        modified = True

                        # Обновляем таймер или удаляем
                        if ev["type"] == "one_time":
                            continue  # Пропускаем добавление в active_events (удаляем)

                        elif ev["type"] == "interval":
                            ev["trigger_at"] += ev["interval_minutes"] * 60
                            active_events.append(ev)

                        elif ev["type"] == "recurring":
                            # Добавляем нужное кол-во дней
                            ev["trigger_at"] += ev["interval_days"] * 86400
                            active_events.append(ev)
                    else:
                        active_events.append(ev)

                if modified:
                    self.client.update_events(active_events)
                    self._update_state_view()

            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Calendar] Ошибка в цикле мониторинга: {e}")

            await asyncio.sleep(self.polling_interval)

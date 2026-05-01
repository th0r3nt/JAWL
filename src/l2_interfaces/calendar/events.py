"""
Фоновый хронометрист (Watchdog времени).

Сравнивает текущий UNIX-timestamp с запланированными задачами. При совпадении —
генерирует системное событие в EventBus, экстренно прерывая сон агента
и передавая ему суть сработавшего будильника.
"""

import time
import asyncio
from typing import Optional

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.calendar_state import CalendarState
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
    ) -> None:
        """
        Инициализирует хронометриста.

        Args:
            client: Экземпляр CalendarClient.
            state: L0 стейт (приборная панель).
            event_bus: Глобальная шина событий.
            polling_interval: Как часто проверять таймеры (в секундах).
        """
        self.client = client
        self.state = state
        self.bus = event_bus
        self.polling_interval = polling_interval

        self._is_running: bool = False
        self._polling_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Запускает фоновый поллинг событий календаря."""
        if self._is_running:
            return

        self._is_running = True
        self.client.state.is_online = True
        self.client.update_state_view()  # Дергаем обновленный метод из клиента

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

    async def _loop(self) -> None:
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

                # Если хотя бы один таймер сработал, перезаписываем JSON
                # Метод _save() клиента внутри update_events автоматически обновит стейт
                if modified:
                    self.client.update_events(active_events)

            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Calendar] Ошибка в цикле мониторинга: {e}")

            await asyncio.sleep(self.polling_interval)

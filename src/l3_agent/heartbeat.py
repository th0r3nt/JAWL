import asyncio
import time
from typing import Dict, Any, TYPE_CHECKING

from src.utils.logger import system_logger
from src.utils.event.registry import EventLevel

if TYPE_CHECKING:
    from src.l3_agent.react.loop import ReactLoop


class Heartbeat:
    """
    Главный пульс агента.
    Управляет таймерами запуска ReAct-цикла.
    Реагирует на внешние раздражители:
    - HIGH/CRITICAL: моментальное пробуждение.
    - MEDIUM: сокращение времени сна на 50%.
    - LOW/BACKGROUND: незначительное сокращение времени сна (на 20%).
    """

    def __init__(self, react_loop: "ReactLoop", tick_interval_sec: int):
        self.react_loop = react_loop
        self.tick_interval_sec = tick_interval_sec

        self._wake_event = asyncio.Event()
        self._is_running = False

        self._next_tick_time = 0.0
        self._wake_reason = "PROACTIVITY"
        self._wake_payload: Dict[str, Any] = {}

    def wake_up(self, level: EventLevel, event_name: str, payload: Dict[str, Any] = None):
        """
        Сдвигает таймер пробуждения в зависимости от важности события.
        Вызывается интерфейсами через EventBus.
        """

        now = time.time()
        payload = payload or {}

        if level >= EventLevel.HIGH:
            # Моментальное пробуждение
            self._wake_reason = event_name
            self._wake_payload = payload
            self._next_tick_time = now
            self._wake_event.set()

        elif level == EventLevel.MEDIUM:
            # Сокращаем оставшееся время сна наполовину
            remaining = self._next_tick_time - now
            if remaining > 0:
                self._next_tick_time = now + (remaining / 2)
                self._wake_event.set()

        elif level <= EventLevel.LOW:
            # Незначительно сокращаем время сна
            remaining = self._next_tick_time - now
            if remaining > 0:
                self._next_tick_time = now + (remaining * 0.8)
                self._wake_event.set()

    async def start(self):
        """Бесконечный цикл сердцебиения."""

        if self._is_running:
            return

        self._is_running = True
        system_logger.info("[System] Heartbeat запущен. Агент переведен в автономный режим.")

        # Инициализируем таймер, только если он еще не был задан событием
        if self._next_tick_time == 0.0:
            self._next_tick_time = time.time() + self.tick_interval_sec

        while self._is_running:
            now = time.time()
            sleep_duration = self._next_tick_time - now

            if sleep_duration > 0:
                self._wake_event.clear()
                try:
                    # Спим. Если вызовут wake_up() - сон прервется для перерасчета таймера
                    await asyncio.wait_for(self._wake_event.wait(), timeout=sleep_duration)

                except asyncio.TimeoutError:
                    # Таймаут истек естественным путем - время для проактивности
                    if self._next_tick_time <= time.time():
                        self._wake_reason = "PROACTIVITY"
                        self._wake_payload = {}

            # Если время пришло (или было сброшено на 'now' из-за HIGH события)
            if time.time() >= self._next_tick_time:
                try:
                    await self.react_loop.run(
                        event_name=self._wake_reason,
                        payload=self._wake_payload,
                    )
                except Exception as e:
                    system_logger.error(f"[System] Критическая ошибка в ReAct-цикле: {e}")

                # Сбрасываем таймер и причину для следующего тика
                self._next_tick_time = time.time() + self.tick_interval_sec
                self._wake_reason = "PROACTIVITY"
                self._wake_payload = {}

    def stop(self):
        """Остановка пульса."""
        self._is_running = False
        self._wake_event.set()
        system_logger.info("[System] Heartbeat остановлен.")

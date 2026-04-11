import asyncio
import time
from datetime import datetime
from collections import deque
from typing import Dict, Any, TYPE_CHECKING

from src.utils.logger import system_logger
from src.utils.event.registry import EventLevel

if TYPE_CHECKING:
    from src.l3_agent.react.loop import ReactLoop
    from src.utils.settings import EventAccelerationConfig


class Heartbeat:
    """
    Главный пульс агента.
    Управляет таймерами запуска ReAct-цикла.
    Реагирует на внешние раздражители:
    - HIGH/CRITICAL: моментальное пробуждение.
    - MEDIUM: сокращение времени сна на 50%.
    - LOW/BACKGROUND: незначительное сокращение времени сна (на 20%).
    """

    def __init__(
        self,
        react_loop: "ReactLoop",
        tick_interval_sec: int,
        accel_config: "EventAccelerationConfig",
    ):
        self.react_loop = react_loop
        self.tick_interval_sec = tick_interval_sec
        self.accel_config = accel_config

        self._wake_event = asyncio.Event()
        self._is_running = False

        self._next_tick_time = 0.0
        self._wake_reason = "HEARTBEAT"
        self._wake_payload: Dict[str, Any] = {}

        # Кольцевой буфер для событий во время сна
        self._sleep_memory = deque(maxlen=20)

    def wake_up(self, level: EventLevel, event_name: str, payload: Dict[str, Any] = None):
        """
        Сдвигает таймер пробуждения в зависимости от важности события.
        Вызывается интерфейсами через EventBus.
        """

        now = time.time()
        payload = payload or {}

        # Записываем ВСЕ события в память сна
        time_str = datetime.now().strftime("%H:%M:%S")
        payload_str = ", ".join(f"{k}={v}" for k, v in payload.items()) if payload else "empty"
        self._sleep_memory.append(
            f"[{time_str}] [{level.name}] {event_name} | Payload: {payload_str}"
        )

        if level >= EventLevel.HIGH:
            # Моментальное пробуждение
            self._wake_reason = event_name
            self._wake_payload = payload
            self._next_tick_time = now
            self._wake_event.set()

        elif level == EventLevel.MEDIUM:
            remaining = self._next_tick_time - now
            if remaining > 0:
                new_remaining = remaining * self.accel_config.medium_multiplier
                saved_seconds = remaining - new_remaining
                self._next_tick_time = now + new_remaining

                system_logger.info(
                    f"[System] Событие {event_name} (Level: MEDIUM). Следующий вызов LLM ускорен на {saved_seconds:.1f} сек."
                )
                self._wake_event.set()

        elif level <= EventLevel.LOW:
            # Незначительно сокращаем время сна
            remaining = self._next_tick_time - now
            if remaining > 0:
                new_remaining = remaining * self.accel_config.low_background_multiplier
                saved_seconds = remaining - new_remaining
                self._next_tick_time = now + new_remaining

                system_logger.info(
                    f"[System] Событие {event_name} (Level: {level.name}). Следующий вызов LLM ускорен на {saved_seconds:.1f} сек."
                )
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
                        self._wake_reason = "HEARTBEAT"
                        self._wake_payload = {}

            # Если время пришло (или было сброшено на 'now' из-за HIGH события)
            if time.time() >= self._next_tick_time:
                # Извлекаем накопленную память и очищаем буфер
                missed_events = list(self._sleep_memory)
                self._sleep_memory.clear()

                try:
                    await self.react_loop.run(
                        event_name=self._wake_reason,
                        payload=self._wake_payload,
                        missed_events=missed_events,
                    )
                except Exception as e:
                    system_logger.error(f"[System] Критическая ошибка в ReAct-цикле: {e}")

                # Сбрасываем таймер и причину для следующего тика
                self._next_tick_time = time.time() + self.tick_interval_sec
                self._wake_reason = "HEARTBEAT"
                self._wake_payload = {}

    def stop(self):
        """Остановка пульса."""
        self._is_running = False
        self._wake_event.set()
        system_logger.info("[System] Heartbeat остановлен.")

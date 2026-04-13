import asyncio
import time
from datetime import datetime, timezone, timedelta
from collections import deque
from typing import Optional, Dict, Any, TYPE_CHECKING

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
    - HIGH/CRITICAL: моментальное пробуждение и отмена текущего цикла.
    - MEDIUM: сокращение времени сна на 50%.
    - LOW/BACKGROUND: незначительное сокращение времени сна (на 20%).
    """

    def __init__(
        self,
        react_loop: "ReactLoop",
        tick_interval_sec: int,
        continuous_cycle: bool,
        accel_config: "EventAccelerationConfig",
        timezone: int,
    ):
        self.react_loop = react_loop
        self.tick_interval_sec = tick_interval_sec
        self.continuous_cycle = continuous_cycle
        self.accel_config = accel_config
        self.timezone = timezone

        self._wake_event = asyncio.Event()
        self._is_running: bool = False

        self._next_tick_time: int = 0.0
        self._wake_reason: str = "HEARTBEAT"
        self._wake_payload: Dict[str, Any] = {}

        self._sleep_memory: deque[str] = deque(maxlen=20)

        # Ссылка на текущую выполняемую задачу ReAct-цикла
        self._active_react_task: Optional[asyncio.Task] = None

    def wake_up(
        self, level: EventLevel, event_name: str, payload: Optional[Dict[str, Any]] = None
    ):
        now = time.time()
        payload = payload or {}

        tz = timezone(timedelta(hours=self.timezone))
        time_str = datetime.now(tz).strftime("%H:%M:%S")
        payload_str = ", ".join(f"{k}={v}" for k, v in payload.items()) if payload else "empty"
        self._sleep_memory.append(
            f"[{time_str}] [{level.name}] {event_name} | Payload: {payload_str}"
        )

        if level >= EventLevel.HIGH:
            self._wake_reason = event_name
            self._wake_payload = payload
            self._next_tick_time = now
            self._wake_event.set()

            # Жесткое прерывание: если агент сейчас думает, убиваем процесс
            if self._active_react_task and not self._active_react_task.done():
                system_logger.warning(
                    f"[System] Прерывание текущего ReAct-цикла из-за события: {event_name}"
                )
                self._active_react_task.cancel()

        elif level == EventLevel.MEDIUM:
            remaining = self._next_tick_time - now
            if remaining > 0:
                new_remaining = remaining * self.accel_config.medium_multiplier
                self._next_tick_time = now + new_remaining
                self._wake_event.set()

        elif level <= EventLevel.LOW:
            remaining = self._next_tick_time - now
            if remaining > 0:
                new_remaining = remaining * self.accel_config.low_background_multiplier
                self._next_tick_time = now + new_remaining
                self._wake_event.set()

    async def start(self) -> None:
        if self._is_running:
            return

        self._is_running = True
        system_logger.info("[System] Heartbeat запущен. Агент переведен в автономный режим.")

        if self._next_tick_time == 0.0:
            self._next_tick_time = time.time() + self.tick_interval_sec

        while self._is_running:
            now = time.time()

            if self.continuous_cycle:
                await asyncio.sleep(0.1)
            else:
                sleep_duration = self._next_tick_time - now
                if sleep_duration > 0:
                    self._wake_event.clear()
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=sleep_duration)
                    except asyncio.TimeoutError:
                        if self._next_tick_time <= time.time():
                            self._wake_reason = "HEARTBEAT"
                            self._wake_payload = {}

            if self.continuous_cycle or time.time() >= self._next_tick_time:
                missed_events = list(self._sleep_memory)
                self._sleep_memory.clear()

                try:
                    # Оборачиваем вызов в Task для возможности прерывания
                    self._active_react_task = asyncio.create_task(
                        self.react_loop.run(
                            event_name=self._wake_reason,
                            payload=self._wake_payload,
                            missed_events=missed_events,
                        )
                    )
                    await self._active_react_task

                    # Сбрасываем причину ТОЛЬКО если цикл завершился сам, без прерываний
                    self._next_tick_time = time.time() + self.tick_interval_sec
                    self._wake_reason = "HEARTBEAT"
                    self._wake_payload = {}

                except asyncio.CancelledError:
                    # Цикл был отменен методом wake_up().
                    # Мы намеренно не сбрасываем _wake_reason, чтобы на следующей итерации
                    # while цикл мгновенно запустился с приоритетными данными.
                    system_logger.info("[System] Текущий ReAct-цикл успешно отменен.")

                except Exception as e:
                    system_logger.error(f"[System] Критическая ошибка в ReAct-цикле: {e}")
                    self._next_tick_time = time.time() + self.tick_interval_sec
                    self._wake_reason = "HEARTBEAT"
                    self._wake_payload = {}

                finally:
                    self._active_react_task = None

    def stop(self) -> None:
        self._is_running = False
        self._wake_event.set()
        if self._active_react_task and not self._active_react_task.done():
            self._active_react_task.cancel()
        system_logger.info("[System] Heartbeat остановлен.")

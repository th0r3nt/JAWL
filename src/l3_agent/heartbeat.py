import asyncio
import time
from collections import deque
from typing import Optional, Dict, Any, TYPE_CHECKING

from src.utils.logger import system_logger
from src.utils.event.registry import EventLevel
from src.utils.dtime import get_now_formatted


if TYPE_CHECKING:
    from src.l3_agent.react.loop import ReactLoop
    from src.utils.settings import EventAccelerationConfig


class Heartbeat:
    """
    Главный пульс агента.
    Управляет таймерами запуска ReAct-цикла.
    Реагирует на внешние раздражители.
    """

    def __init__(
        self,
        react_loop: "ReactLoop",
        heartbeat_interval: int,
        continuous_cycle: bool,
        accel_config: "EventAccelerationConfig",
        timezone: int,
    ):
        self.react_loop = react_loop
        self.heartbeat_interval = heartbeat_interval
        self.continuous_cycle = continuous_cycle
        self.accel_config = accel_config
        self.timezone = timezone

        self._wake_event = asyncio.Event()
        self._is_running: bool = False

        self._next_tick_time: int = 0.0
        self._wake_reason: str = "HEARTBEAT"
        self._wake_payload: Dict[str, Any] = {}
        self._wake_level: int = 0  # Приоритет текущего триггера

        self._sleep_memory: deque[str] = deque(maxlen=20)

        # Ссылка на текущую выполняемую задачу ReAct-цикла
        self._active_react_task: Optional[asyncio.Task] = None

        # Флаг намеренного прерывания, чтобы отличать логику агента от Ctrl+C
        self._is_interrupted: bool = False

    def answer_to_event(
        self, level: EventLevel, event_name: str, payload: Optional[Dict[str, Any]] = None
    ):
        """Смотрит на входящее событие и решает, вызывать ли агента."""

        now = time.time()
        payload = payload or {}
        time_str = get_now_formatted(self.timezone, fmt="%H:%M:%S")

        event_data = {
            "time": time_str,
            "level": level.name,
            "name": event_name,
            "payload": payload,
        }

        # Определяем множитель важности события
        multiplier = 1.0
        if level == EventLevel.CRITICAL:
            multiplier = self.accel_config.critical_multiplier

        elif level == EventLevel.HIGH:
            multiplier = self.accel_config.high_multiplier

        elif level == EventLevel.MEDIUM:
            multiplier = self.accel_config.medium_multiplier

        elif level == EventLevel.LOW:
            multiplier = self.accel_config.low_multiplier
        elif level == EventLevel.BACKGROUND:
            multiplier = self.accel_config.background_multiplier

        is_awake = self._active_react_task and not self._active_react_task.done()

        # =========================================================
        # Логика для бодрствующего в данный момент агента
        # =========================================================

        if is_awake:
            # Пробрасываем событие прямо в активный цикл
            self.react_loop.add_realtime_event(event_data)

            # Если множитель 0.0 - это жесткое прерывание текущего процесса (например, SYSTEM_SHUTDOWN)
            if multiplier <= 0.01:
                system_logger.warning(
                    f"[Heartbeat] Прерывание текущего ReAct-цикла из-за события: {event_name}"
                )
                self._wake_reason = event_name
                self._wake_payload = payload
                self._wake_level = level.value
                self._is_interrupted = True
                self._active_react_task.cancel()

            # Таймер следующего сна (_next_tick_time) НЕ трогаем
            return

        # =========================================================
        # Логика для спящего в данный момент агента
        # =========================================================

        self._sleep_memory.append(event_data)

        remaining = self._next_tick_time - now

        # Если множитель < 1, значит событие должно повлиять на таймер
        if multiplier < 1.0:
            # Защита от отрицательного remaining (если Heartbeat только стартовал)
            safe_remaining = max(0.0, remaining)

            new_remaining = safe_remaining * multiplier
            reduced_by = safe_remaining - new_remaining

            self._next_tick_time = now + new_remaining
            self._wake_event.set()

            # Если сон срезан в ноль - это экстренное пробуждение
            if new_remaining <= 0.01:
                # Перезаписываем главную причину, только если новое событие важнее или такое же
                if level.value >= self._wake_level:
                    system_logger.info(
                        f"[Heartbeat] Входящее событие: '{event_name}' ({level.name}). Инициализация вызова LLM."
                    )
                    self._wake_reason = event_name
                    self._wake_payload = payload
                    self._wake_level = level.value
                else:
                    system_logger.info(
                        f"[Heartbeat] Входящее событие: '{event_name}' ({level.name}). Сон уже прерван более приоритетным событием."
                    )
            else:
                if safe_remaining > 0:
                    system_logger.info(
                        f"[Heartbeat] Входящее событие: '{event_name}' ({level.name}). Следующий вызов LLM сокращен на {reduced_by:.1f} сек. До пробуждения: {new_remaining:.1f} сек."
                    )

    async def start(self) -> None:
        if self._is_running:
            return

        self._is_running = True
        system_logger.info("[Heartbeat] Агент переведен в автономный режим.")

        if self._next_tick_time == 0.0:
            self._next_tick_time = time.time() + self.heartbeat_interval

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

                # Убираем дублирование: если событие стало главным триггером, удаляем его из лога (missed_events)
                if self._wake_reason != "HEARTBEAT":
                    for i in range(len(missed_events) - 1, -1, -1):
                        if (
                            missed_events[i]["name"] == self._wake_reason
                            and missed_events[i]["payload"] == self._wake_payload
                        ):
                            missed_events.pop(i)
                            break

                # Устанавливаем таймер ДО начала работы агента
                # Фоновые события, приходящие во время бодрствования,
                # будут корректно сокращать будущий сон и высвечиваться в логах
                self._next_tick_time = time.time() + self.heartbeat_interval

                try:
                    self._active_react_task = asyncio.create_task(
                        self.react_loop.run(
                            event_name=self._wake_reason,
                            payload=self._wake_payload,
                            missed_events=missed_events,
                        )
                    )
                    await self._active_react_task

                    # Сбрасываем причину только если цикл завершился сам, без прерываний
                    self._wake_reason = "HEARTBEAT"
                    self._wake_payload = {}

                except asyncio.CancelledError:
                    if self._is_interrupted:
                        # Отмена инициирована нами (answer_to_event). Глотаем ошибку и идем на новый круг
                        system_logger.info("[System] Текущий ReAct-цикл успешно прерван.")
                        self._is_interrupted = False
                    else:
                        raise

                except Exception as e:
                    system_logger.error(f"[System] Критическая ошибка в ReAct-цикле: {e}")
                    # При краше сбрасываем таймер заново, чтобы не уйти в бесконечный луп ошибок
                    self._next_tick_time = time.time() + self.heartbeat_interval
                    self._wake_reason = "HEARTBEAT"
                    self._wake_payload = {}

                finally:
                    self._active_react_task = None

    def stop(self) -> None:
        self._is_running = False
        self._wake_event.set()
        if self._active_react_task and not self._active_react_task.done():
            self._is_interrupted = True
            self._active_react_task.cancel()
        system_logger.info("[Heartbeat] Остановка завершена.")

    def update_config(self, key: str, value: Any):
        """Метод для динамического обновления настроек на лету (по сигналу из EventBus)."""

        if key == "heartbeat_interval":
            self.heartbeat_interval = int(value)
            system_logger.info(
                f"[System] Heartbeat обновил интервал на {self.heartbeat_interval} сек."
            )

        elif key == "continuous_cycle":
            self.continuous_cycle = bool(value)
            system_logger.info(
                f"[System] Heartbeat обновил continuous_cycle на {self.continuous_cycle}."
            )

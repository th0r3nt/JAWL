"""
Мост маршрутизации системных событий.

Отделяет логику подписки (EventBus) от главного файла. Слушает шину
событий и пробрасывает триггеры в Heartbeat агента, а также обрабатывает
системные команды на выключение/ребут и изменение конфигов в рантайме.
"""

from typing import TYPE_CHECKING, Any, Callable, Coroutine

from src.utils.logger import main_logger
from src.utils.event.registry import Events, EventConfig

if TYPE_CHECKING:
    from src.system.container import SystemContainer


class EventBridge:
    """Маршрутизатор системных событий (Event-Driven паттерн)."""

    def __init__(self, container: "SystemContainer"):
        self.container = container

    def setup_routing(self) -> None:
        """Подписывает Heartbeat и системные триггеры на все события из EventBus."""

        # Специфичные системные подписки
        self.container.event_bus.subscribe(
            Events.SYSTEM_SHUTDOWN_REQUESTED, self._handle_shutdown
        )
        self.container.event_bus.subscribe(Events.SYSTEM_REBOOT_REQUESTED, self._handle_reboot)
        self.container.event_bus.subscribe(
            Events.SYSTEM_CONFIG_UPDATED, self._handle_config_update
        )
        self.container.event_bus.subscribe(
            Events.SYSTEM_DASHBOARD_UPDATE, self._handle_dashboard_update
        )

        # Подписка Heartbeat на остальные события (динамическая генерация)
        system_events = {
            Events.SYSTEM_CORE_STOP.name,
            Events.SYSTEM_SHUTDOWN_REQUESTED.name,
            Events.SYSTEM_REBOOT_REQUESTED.name,
        }

        for event in Events.all():
            if event.name in system_events:
                continue

            # Замыкание для фиксации текущего event в контексте генератора
            handler = self._create_heartbeat_handler(event)
            self.container.event_bus.subscribe(event, handler)

    def _create_heartbeat_handler(
        self, evt: EventConfig
    ) -> Callable[..., Coroutine[Any, Any, None]]:
        """
        Генерирует асинхронный обработчик для перенаправления события в Heartbeat.
        """

        async def handler(**kwargs: Any) -> None:
            if evt == Events.SYSTEM_CORE_STOP:
                return

            if self.container.heartbeat:
                self.container.heartbeat.answer_to_event(
                    level=evt.level, event_name=evt.name, payload=kwargs
                )

        return handler

    # =========================================================================
    # ОБРАБОТЧИКИ СИСТЕМНЫХ КОМАНД И КОНФИГУРАЦИЙ
    # =========================================================================

    async def _handle_config_update(self, **kwargs: Any) -> None:
        """
        Рантайм-обновление настроек подсистем (Hot Reload).
        """

        key = kwargs.get("key")

        # Настройки Heartbeat
        if key in ("heartbeat_interval", "continuous_cycle"):
            if self.container.heartbeat:
                self.container.heartbeat.update_config(key, kwargs.get("value"))

        # Лимиты SQL баз данных
        elif key == "db_limit":
            module = kwargs.get("module", "")
            val = kwargs.get("value", 0)

            if self.container.sql:
                self.container.sql.update_limits(module, val)
                main_logger.info(f"[System] Рантайм-обновление лимита для {module}: {val}")

        # Глубина контекста (Ticks)
        elif key == "context_depth":
            high = kwargs.get("high_ticks", 0)
            medium = kwargs.get("medium_ticks", 0)
            low = kwargs.get("low_ticks", 0)

            if self.container.sql:
                self.container.sql.update_context_depth(high, medium, low)

            total = high + medium + low
            main_logger.info(f"[System] Рантайм-обновление контекста: {total} тиков")

    async def _handle_dashboard_update(self, **kwargs: Any) -> None:
        """
        Обновление или удаление кастомного блока Markdown на дашборде L0 State.
        """

        name = kwargs.get("name")
        content = kwargs.get("content")

        if name and self.container.dashboard_state:
            self.container.dashboard_state.update_block(name, content)

    async def _handle_shutdown(self, **kwargs: Any) -> None:
        """
        Команда на выключение системы.
        """

        self.container.exit_code = 0
        if self.container.heartbeat:
            self.container.heartbeat.stop()

    async def _handle_reboot(self, **kwargs: Any) -> None:
        """
        Команда на перезагрузку системы.
        """
        
        self.container.exit_code = 1
        if self.container.heartbeat:
            self.container.heartbeat.stop()

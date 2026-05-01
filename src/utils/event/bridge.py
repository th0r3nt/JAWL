"""
Мост маршрутизации системных событий (Event Bridge).

Отделяет логику подписки (EventBus) от главного файла main.py.
Слушает шину событий и пробрасывает триггеры в Heartbeat агента,
а также обрабатывает системные команды на выключение/ребут и изменение конфигов.
"""

from typing import TYPE_CHECKING

from src.utils.logger import system_logger
from src.utils.event.registry import Events

if TYPE_CHECKING:
    from src.main import System


class EventBridge:
    """Маршрутизатор системных событий (Event-Driven паттерн)."""

    def __init__(self, system: "System"):
        self.system = system

    def setup_routing(self) -> None:
        """Подписывает Heartbeat и системные триггеры на все события из EventBus."""

        def create_handler(evt):
            # АСИНХРОННЫЙ ХЕНДЛЕР: гарантирует потокобезопасность при Event.set() в Heartbeat
            async def handler(**kwargs):
                # Если система уже останавливается - игнорируем любые события
                if evt == Events.SYSTEM_CORE_STOP:
                    return

                if self.system.heartbeat:
                    self.system.heartbeat.answer_to_event(
                        level=evt.level, event_name=evt.name, payload=kwargs
                    )

            return handler

        # Базовая подписка: будим агента на любые события, кроме остановки
        for event in Events.all():
            if event.name in (
                Events.SYSTEM_CORE_STOP.name,
                Events.SYSTEM_SHUTDOWN_REQUESTED.name,
                Events.SYSTEM_REBOOT_REQUESTED.name,
            ):
                continue
            self.system.event_bus.subscribe(event, create_handler(event))

        # Специфичные подписки (сделаны асинхронными для единообразия и стабильности)
        async def handle_config_update(**kwargs):
            key = kwargs.get("key")

            # Настройки Heartbeat
            if key in ("heartbeat_interval", "continuous_cycle"):
                if self.system.heartbeat:
                    self.system.heartbeat.update_config(key, kwargs.get("value"))

            # Лимиты SQL баз данных
            elif key == "db_limit":
                module = kwargs.get("module")
                val = kwargs.get("value")
                if self.system.sql:
                    if module == "tasks":
                        self.system.sql.tasks.max_tasks = val
                    elif module == "personality_traits":
                        self.system.sql.personality_traits.max_traits = val
                    elif module == "mental_states":
                        self.system.sql.mental_states.max_entities = val
                    elif module == "drives_custom":
                        self.system.sql.drives.max_custom = val

                system_logger.info(f"[System] Рантайм-обновление лимита для {module}: {val}")

            # Глубина контекста
            elif key == "context_depth":
                if self.system.sql:
                    self.system.sql.ticks.ticks_limit = kwargs.get("total_ticks")
                    self.system.sql.ticks.detailed_ticks = kwargs.get("detailed_ticks")

                system_logger.info(
                    f"[System] Рантайм-обновление контекста: {kwargs.get('total_ticks')} тиков"
                )

        async def handle_dashboard_update(**kwargs):
            name = kwargs.get("name")
            content = kwargs.get("content")
            if name:
                if content:
                    self.system.dashboard_state.blocks[name] = content
                else:
                    self.system.dashboard_state.blocks.pop(name, None)

        # Если агент решил совершить сэппуку
        async def handle_shutdown(**kwargs):
            self.system._exit_code = 0
            if self.system.heartbeat:
                self.system.heartbeat.stop()

        # Если агент запросил перезагрузку
        async def handle_reboot(**kwargs):
            self.system._exit_code = 1
            if self.system.heartbeat:
                self.system.heartbeat.stop()

        self.system.event_bus.subscribe(Events.SYSTEM_SHUTDOWN_REQUESTED, handle_shutdown)
        self.system.event_bus.subscribe(Events.SYSTEM_REBOOT_REQUESTED, handle_reboot)
        self.system.event_bus.subscribe(Events.SYSTEM_CONFIG_UPDATED, handle_config_update)
        self.system.event_bus.subscribe(
            Events.SYSTEM_DASHBOARD_UPDATE, handle_dashboard_update
        )

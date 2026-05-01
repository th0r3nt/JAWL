"""
Фоновый слушатель/воркер (Events Poller) пользовательского интерфейса.

Этот модуль работает в фоне (асинхронный бесконечный цикл) и ждет входящих событий
от внешнего мира. Когда событие происходит, воркер публикует его в `EventBus`,
что заставляет агента проснуться быстрее.
"""

import asyncio
from typing import Optional, Any

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus

# В реальном коде вам нужно зарегистрировать свой ивент (например EXAMPLE_INCOMING)
# в src/utils/event/registry.py (написать эвент EXAMPLE_INCOMING в Events)
# from src.utils.event.registry import Events


class ExampleEvents:
    """Слушатель событий (Webhooks, Long Polling, WebSockets)."""

    def __init__(self, client: Any, event_bus: EventBus) -> None:
        self.client = client
        self.bus = event_bus
        self._is_running = False
        self._polling_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Запускает фоновый процесс прослушивания."""
        if self._is_running:
            return

        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        system_logger.info("[Example] Фоновый воркер запущен.")

    async def stop(self) -> None:
        """Останавливает фоновый процесс."""
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        system_logger.info("[Example] Фоновый воркер остановлен.")

    async def _loop(self) -> None:
        """
        Бесконечный цикл, который опрашивает API или ждет данные из сокета.
        """
        while self._is_running:
            try:
                # 1. Запрос к серверу через клиент
                # new_data = await self.client.fetch_new_data()
                new_data = None  # Заглушка

                if new_data:
                    # 2. Обязательно обновляем L0 State, чтобы агент мог прочитать это в контексте
                    # self.client.state.last_data = new_data

                    # 3. Публикуем событие в шину (пробуждаем агента)
                    # await self.bus.publish(
                    #     Events.EXAMPLE_INCOMING,
                    #     message="Новое событие из сервиса",
                    #     payload_data=new_data
                    # )
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Example] Ошибка в фоновом цикле: {e}")

            # Обязательно делаем паузу, чтобы к чертям не заблочить главный Event Loop
            await asyncio.sleep(60)

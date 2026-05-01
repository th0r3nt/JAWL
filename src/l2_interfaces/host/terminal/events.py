"""
Оркестратор событий терминала.
Выступает мостом (Consumer) между внутренней асинхронной очередью TCP-сервера 
и глобальной шиной событий (EventBus).
"""

import asyncio
from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.l2_interfaces.host.terminal.client import HostTerminalClient


class HostTerminalEvents:
    """Фоновый воркер: перекладывает сообщения и события подключения из очереди сокета в EventBus."""

    def __init__(self, client: HostTerminalClient, event_bus: EventBus):
        self.client = client
        self.bus = event_bus
        self._task = None
        self._is_running = False

    async def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        while self._is_running:
            try:
                # Ждем данные из TCP-сервера
                action, payload = await self.client.incoming_queue.get()

                # Публикуем соответствующее событие
                if action == "_CONNECTION_OPENED":
                    await self.bus.publish(
                        Events.HOST_TERMINAL_OPENED,
                        message="Пользователь открыл терминал чата и смотрит в него.",
                    )
                elif action == "_CONNECTION_CLOSED":
                    await self.bus.publish(
                        Events.HOST_TERMINAL_CLOSED,
                        message="Пользователь закрыл терминал чата.",
                    )
                elif action == "_MESSAGE":
                    await self.bus.publish(
                        Events.HOST_TERMINAL_MESSAGE, sender_name="User", message=payload
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка в обработке терминала: {e}")

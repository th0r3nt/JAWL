import asyncio
from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.l2_interfaces.host.terminal.client import HostTerminalClient


class HostTerminalEvents:
    """Фоновый воркер: перекладывает сообщения из очереди сокета в EventBus."""

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
                # Ждем сообщение из TCP-сервера
                text = await self.client.incoming_queue.get()

                # Публикуем событие, чтобы разбудить Heartbeat
                await self.bus.publish(
                    Events.HOST_TERMINAL_MESSAGE, sender_name="User", message=text
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.error(f"[Host OS] Ошибка в обработке терминала: {e}")

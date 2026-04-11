import asyncio

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.logger import system_logger

from src.l0_state.interfaces.state import HostTerminalState
from src.l2_interfaces.host.terminal.client import HostTerminalClient


class HostTerminalEvents:
    """
    Фоновый слушатель локального терминала.
    Ждет ввода от админа, обновляет стейт и будит агента.
    """

    def __init__(
        self, client: HostTerminalClient, state: HostTerminalState, event_bus: EventBus
    ):
        self.client = client
        self.state = state
        self.bus = event_bus

        self._is_running = False
        self._listen_task: asyncio.Task | None = None

    async def start(self):
        """Запускает фоновое чтение очереди сообщений."""
        if not self.client.config.enabled or self._is_running:
            return

        self._is_running = True
        self._listen_task = asyncio.create_task(self._loop())
        system_logger.info("[System] HostTerminalEvents: Слушатель терминала запущен.")

    async def stop(self):
        """Останавливает слушатель."""
        self._is_running = False

        if self._listen_task:
            self._listen_task.cancel()
            self._listen_task = None

        system_logger.info("[System] HostTerminalEvents: Слушатель терминала остановлен.")

    def _update_state(self, message: str):
        """Обновляет историю сообщений в приборной панели (L0), соблюдая лимит."""
        lines = self.state.messages.split("\n") if self.state.messages else []
        lines.append(f"Admin: {message}")

        # Оставляем только последние N сообщений
        if len(lines) > self.state.number_of_last_messages:
            lines = lines[-self.state.number_of_last_messages :]

        self.state.messages = "\n".join(lines)

    async def _loop(self):
        while self._is_running:
            try:
                # Ждем сообщение из очереди клиента
                message = await self.client.incoming_messages.get()

                # Записываем в приборную панель агента
                self._update_state(message)

                # Публикуем событие, чтобы разбудить агента
                await self.bus.publish(
                    Events.TERMINAL_MESSAGE_INCOMING,
                    message=message,
                    sender_name="Admin",
                )

            except asyncio.CancelledError:
                break

            except Exception as e:
                system_logger.error(f"[System] Ошибка в цикле HostTerminalEvents: {e}")

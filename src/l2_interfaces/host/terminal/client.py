import asyncio
from src.utils.logger import system_logger
from src.utils.settings import HostTerminalConfig
from src.l0_state.interfaces.state import HostTerminalState


class HostTerminalClient:
    """
    Адаптер терминала.
    Поднимает локальный TCP-сокет. Клиентское UI-окно (src/cli/...)
    подключается к нему для двустороннего обмена сообщениями.
    """

    def __init__(
        self,
        config: HostTerminalConfig,
        state: HostTerminalState,
        host: str = "127.0.0.1",
        port: int = 50505,
    ):
        self.config = config
        self.state = state
        self.host = host
        self.port = port

        self._server: asyncio.Server | None = None
        self._writer: asyncio.StreamWriter | None = None  # Подключенное окно терминала

        # Очередь для передачи входящих сообщений в events.py
        self.incoming_messages = asyncio.Queue()

    async def start(self) -> None:
        """Запускает сокет-сервер."""

        if not self.config.enabled:
            return

        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        system_logger.info(f"[Terminal] Сервер интерфейса запущен на {self.host}:{self.port}")
        self.state.is_online = True

    async def stop(self) -> None:
        """Корректно закрывает соединения."""

        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        system_logger.info("[Terminal] Сервер интерфейса остановлен.")
        self.state.is_online = False

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Обрабатывает подключение UI-клиента (окна)."""

        # Если кто-то уже подключен - отключаем старого (одновременно только 1 окно)
        if self._writer:
            self._writer.close()

        self._writer = writer
        peer = writer.get_extra_info("peername")
        system_logger.info(f"[Terminal] Окно терминала подключено: {peer}")
        self.state.is_ui_connected = True

        try:
            while True:
                data = await reader.readline()
                if not data:
                    break  # Клиент закрыл окно/отключился

                message = data.decode("utf-8").strip()
                if message:
                    await self.incoming_messages.put(message)

        except asyncio.CancelledError:
            pass

        except Exception as e:
            system_logger.error(f"[Terminal] Ошибка соединения с окном: {e}")

        finally:
            system_logger.info("[Terminal] Окно терминала отключено.")
            self._writer = None
            self.state.is_ui_connected = False

    async def send_message(self, text: str) -> bool:
        """Отправляет сообщение агента в подключенное UI-окно."""

        if not self._writer:
            system_logger.warning(
                "[Terminal] Попытка отправки сообщения, но окно терминала не подключено."
            )
            return False

        try:
            self._writer.write(f"{text}\n".encode("utf-8"))
            await self._writer.drain()
            return True

        except Exception as e:
            system_logger.error(f"[Terminal] Ошибка при отправке сообщения в окно: {e}")
            return False

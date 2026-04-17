from telethon import TelegramClient
from src.utils.logger import system_logger
from src.l0_state.interfaces.state import TelethonState


class TelethonClient:
    """
    Управляет подключением к Telegram через User API.
    Хранит сессию локально в файле.
    """

    def __init__(
        self,
        state: TelethonState,
        api_id: int,
        api_hash: str,
        session_path: str,
        timezone: int,
    ):
        self.state = state

        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = (
            session_path  # В идеале это src/utils/local/data/telethon/agent_telethon.session
        )
        self.timezone = timezone
        self._client: TelegramClient | None = None

    def client(self) -> TelegramClient:
        """Безопасный доступ к инстансу Telethon."""
        if not self._client:
            raise RuntimeError("TelethonClient не запущен.")
        return self._client

    async def start(self) -> None:
        """
        Запускает клиента.
        При первом запуске попросит ввести номер и код в консоли.
        """
        system_logger.info("[Telegram Telethon] Инициализация клиента.")

        try:
            self._client = TelegramClient(self.session_path, self.api_id, self.api_hash)

            # Встроенная магия Telethon для авторизации через консоль
            await self._client.start()

            me = await self._client.get_me()
            name = me.username or me.first_name or "Unknown"

            system_logger.info(f"[Telegram Telethon] Успешная авторизация как: {name}")
            self.state.is_online = True

        except Exception as e:
            system_logger.error(f"[Telegram Telethon] Критическая ошибка при запуске: {e}")
            raise e

    async def stop(self) -> None:
        """Корректно закрывает соединение."""

        if self._client and self._client.is_connected():
            await self._client.disconnect()
            system_logger.info("[Telegram Telethon] Клиент отключен.")
            self.state.is_online = False

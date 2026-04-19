from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest

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

            # Сразу после старта стягиваем полные данные
            await self.update_profile_state()

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

    async def update_profile_state(self) -> None:
        """Запрашивает актуальные данные аккаунта (имя, юзернейм, био) и сохраняет в стейт."""
        if not self._client:
            return

        try:
            me = await self._client.get_me()
            name = me.first_name or "Unknown"
            if getattr(me, "last_name", None):
                name += f" {me.last_name}"

            username = f"@{me.username}" if me.username else "Без @username"

            # Для получения "о себе" (bio) нужен FullUser запрос
            full_me = await self._client(GetFullUserRequest(me))
            bio = full_me.full_user.about or "Пусто"

            self.state.account_info = f"Профиль: {name} ({username}) | Био: {bio}\n---"
        except Exception as e:
            system_logger.error(f"[Telegram Telethon] Ошибка обновления профиля: {e}")
            self.state.account_info = "Профиль: Ошибка загрузки данных\n---"

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Возвращает отформатированный блок контекста для агента.
        """

        if not self.state.is_online:
            return "### TELETHON [OFF]\nИнтерфейс отключен."

        return f"### TELETHON [ON]\nAccount info: {self.state.account_info}\n{self.state.last_chats}"

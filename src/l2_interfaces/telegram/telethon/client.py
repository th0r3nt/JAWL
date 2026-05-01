"""
Stateful-клиент для работы с Telegram User API (Telethon).

Хранит сессию локально в SQLite-файле (Session File).
Обеспечивает авторизацию через терминал при первом запуске (ручной ввод номера и кода)
и предоставляет провайдер контекста с информацией о профиле и чатах агента.
"""

from typing import Any, Optional
from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest

from src.utils.logger import system_logger
from src.l0_state.interfaces.telegram.telethon_state import TelethonState


class TelethonClient:
    """
    Менеджер подключения к серверам Telegram и управления сессией аккаунта.
    """

    def __init__(
        self,
        state: TelethonState,
        api_id: int,
        api_hash: str,
        session_path: str,
        timezone: int,
    ) -> None:
        """
        Инициализирует клиент.

        Args:
            state (TelethonState): Приборная панель L0.
            api_id (int): API ID приложения Telegram.
            api_hash (str): Hash приложения Telegram.
            session_path (str): Путь для сохранения .session файла на диске.
            timezone (int): Смещение часового пояса (для форматирования логов).
        """
        self.state = state

        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.timezone = timezone

        self._client: Optional[TelegramClient] = None

    def client(self) -> TelegramClient:
        """
        Безопасный доступ к инстансу Telethon.

        Returns:
            TelegramClient: Активный клиент Telethon.

        Raises:
            RuntimeError: Если `start()` еще не был вызван.
        """
        if not self._client:
            raise RuntimeError("TelethonClient не запущен. Инстанс недоступен.")
        return self._client

    async def start(self) -> None:
        """
        Запускает клиента и устанавливает соединение.
        При отсутствии сессии на диске запрашивает ввод номера и кода прямо
        в консоли сервера (механизм библиотеки Telethon).

        Raises:
            Exception: При сетевых сбоях или фатальных ошибках MTProto.
        """
        system_logger.info("[Telegram Telethon] Инициализация клиента.")

        try:
            self._client = TelegramClient(self.session_path, self.api_id, self.api_hash)

            # Встроенная магия Telethon для консольной авторизации
            await self._client.start()

            me = await self._client.get_me()
            name = me.username or me.first_name or "Unknown"

            # Сразу после старта стягиваем полные данные о профиле
            await self.update_profile_state()

            system_logger.info(f"[Telegram Telethon] Успешная авторизация как: @{name}")
            self.state.is_online = True

        except Exception as e:
            system_logger.error(f"[Telegram Telethon] Критическая ошибка при запуске: {e}")
            raise e

    async def stop(self) -> None:
        """Корректно отключается от серверов Telegram."""
        if self._client and self._client.is_connected():
            await self._client.disconnect()
            system_logger.info("[Telegram Telethon] Клиент отключен.")
            self.state.is_online = False

    async def update_profile_state(self) -> None:
        """
        Выполняет GetFullUserRequest для обновления данных профиля агента
        в L0 State (имя, username, bio, личный канал).
        """
        if not self._client:
            return

        try:
            me = await self._client.get_me()
            name = me.first_name or "Unknown"
            if getattr(me, "last_name", None):
                name += f" {me.last_name}"

            username = f"@{me.username}" if me.username else "Без @username"

            # Для получения "о себе" (bio) и личного канала нужен FullUser запрос
            full_me = await self._client(GetFullUserRequest(me))
            bio = full_me.full_user.about or "Пусто"

            # Ищем личный канал (Personal Channel)
            channel_info = ""
            personal_channel_id = getattr(full_me.full_user, "personal_channel_id", None)

            if personal_channel_id:
                try:
                    from telethon import utils

                    channel = await self._client.get_entity(personal_channel_id)
                    channel_name = utils.get_display_name(channel)
                    channel_username = getattr(channel, "username", None)
                    un_str = f" (@{channel_username})" if channel_username else ""

                    channel_info = (
                        f"\nЛичный канал: {channel_name}{un_str} (ID: {personal_channel_id})"
                    )
                except Exception:
                    channel_info = f"\nЛичный канал: ID {personal_channel_id}"

            self.state.account_info = (
                f"Профиль: {name} ({username}) | Био: {bio}{channel_info}\n---"
            )
        except Exception as e:
            system_logger.error(f"[Telegram Telethon] Ошибка обновления профиля: {e}")
            self.state.account_info = "Профиль: Ошибка загрузки данных\n---"

    async def get_context_block(self, **kwargs: Any) -> str:
        """Провайдер контекста для ContextRegistry."""
        if not self.state.is_online:
            return "### TELETHON [OFF]\nИнтерфейс отключен."

        return f"### TELETHON [ON] \nAccount info: {self.state.account_info}\nВАЖНО: рекомендуется отвечать пользователям, у которых стоит UNREAD. \n\n{self.state.last_chats}"

from aiogram import Bot
from src.utils.logger import system_logger
from src.l0_state.interfaces.state import AiogramState

class AiogramClient:
    """
    Управляет базовым подключением к Telegram через Bot API (Aiogram v3).
    Хранит инстанс бота и управляет его сессией.
    """

    def __init__(self, bot_token: str, state: AiogramState):
        self.state = state

        if not bot_token:
            raise ValueError("Для работы Aiogram необходим bot_token.")

        self.bot_token = bot_token
        self._bot: Bot | None = None

    def bot(self) -> Bot:
        """Безопасный доступ к инстансу Aiogram."""
        if not self._bot:
            raise RuntimeError("AiogramClient не запущен.")
        return self._bot

    async def start(self) -> None:
        """
        Инициализирует бота и проверяет токен.
        """
        system_logger.info("[System] Инициализация Aiogram клиента.")

        try:
            self._bot = Bot(token=self.bot_token)

            # Делаем тестовый запрос для проверки токена
            me = await self._bot.get_me()
            system_logger.info(f"[System] Aiogram успешно авторизован как бот: @{me.username}")
            self.state.is_online = True

        except Exception as e:
            system_logger.error(f"[System] Критическая ошибка при запуске Aiogram: {e}")
            raise e

    async def stop(self) -> None:
        """Корректно закрывает сессию aiohttp."""
        
        if self._bot:
            await self._bot.session.close()
            system_logger.info("[System] Aiogram клиент отключен.")
            self.state.is_online = False

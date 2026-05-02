"""
Stateful-клиент для работы с Telegram Bot API (через библиотеку Aiogram v3).

Управляет сессией aiohttp, хранит инстанс бота и предоставляет провайдер контекста
(дашборд последних диалогов) для системного промпта агента.
"""

from typing import Any, Optional
from aiogram import Bot
from src.utils.logger import system_logger
from src.l2_interfaces.telegram.aiogram.state import AiogramState


class AiogramClient:
    """
    Управляет базовым подключением к Telegram через Bot API.
    Гарантирует безопасное открытие и закрытие HTTP сессий.
    """

    def __init__(self, bot_token: str, state: AiogramState) -> None:
        """
        Инициализирует клиент бота.

        Args:
            bot_token (str): Токен, выданный @BotFather.
            state (AiogramState): L0 стейт (приборная панель агента) для хранения MRU-кэша чатов.

        Raises:
            ValueError: Если токен бота пуст.
        """

        self.state = state

        if not bot_token:
            raise ValueError("Для работы Aiogram необходим bot_token.")

        self.bot_token = bot_token
        self._bot: Optional[Bot] = None

    def bot(self) -> Bot:
        """
        Безопасный геттер для получения инстанса бота.

        Returns:
            Bot: Экземпляр aiogram.Bot.

        Raises:
            RuntimeError: Если клиент еще не был запущен через `start()`.
        """

        if not self._bot:
            raise RuntimeError("AiogramClient не запущен. Инстанс бота недоступен.")
        return self._bot

    async def start(self) -> None:
        """
        Инициализирует бота и делает тестовый запрос (get_me) для валидации токена.
        Помечает интерфейс как Online в случае успеха.

        Raises:
            Exception: При невалидном токене или сетевой ошибке.
        """

        system_logger.info("[Telegram Aiogram] Инициализация Aiogram клиента.")

        try:
            self._bot = Bot(token=self.bot_token)

            # Делаем тестовый запрос для проверки токена
            me = await self._bot.get_me()
            system_logger.info(
                f"[Telegram Aiogram] Aiogram успешно авторизован как бот: @{me.username}"
            )
            self.state.is_online = True

        except Exception as e:
            system_logger.error(
                f"[Telegram Aiogram] Критическая ошибка при запуске Aiogram: {e}"
            )
            raise e

    async def stop(self) -> None:
        """
        Корректно закрывает сессию aiohttp и помечает интерфейс как Offline.
        """

        if self._bot:
            await self._bot.session.close()
            system_logger.info("[Telegram Aiogram] Aiogram клиент отключен.")
            self.state.is_online = False

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает отформатированный список последних активных чатов.

        Returns:
            str: Markdown-строка с контекстом.
        """

        if not self.state.is_online:
            return "### AIOGRAM [OFF] \nИнтерфейс отключен."

        return f"### AIOGRAM [ON] \n{self.state.last_chats}"

import asyncpraw
from src.l0_state.interfaces.state import RedditState
from src.utils.logger import system_logger
from src.utils.settings import RedditConfig


class RedditClient:
    """
    Клиент для работы с Reddit API (через asyncpraw).
    В текущей версии реализован только Read-Only режим.
    """

    def __init__(
        self,
        config: RedditConfig,
        state: RedditState,
        client_id: str,
        client_secret: str,
        user_agent: str = "JAWL_Agent",
    ):
        self.config = config
        self.state = state
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent

        self._reddit: asyncpraw.Reddit | None = None

    def reddit(self) -> asyncpraw.Reddit:
        """Безопасный доступ к инстансу asyncpraw."""

        if not self._reddit:
            raise RuntimeError("RedditClient не запущен.")
        return self._reddit

    async def start(self) -> None:
        """Инициализирует сессию."""

        system_logger.info("[Reddit] Инициализация клиента.")
        try:
            self._reddit = asyncpraw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
            )

            # Проверяем режим Read-Only
            read_only = self._reddit.read_only
            mode = "Read-Only" if read_only else "Account"

            system_logger.info(f"[Reddit] Клиент успешно авторизован (Режим: {mode}).")
            self.state.is_online = True

        except Exception as e:
            system_logger.error(f"[Reddit] Критическая ошибка при запуске клиента: {e}")
            raise e

    async def stop(self) -> None:
        """Корректно закрывает aiohttp сессию."""

        if self._reddit:
            await self._reddit.close()
            system_logger.info("[Reddit] Клиент отключен.")
            self.state.is_online = False

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает блок активности агента в промпт.
        """
        
        if not self.state.is_online:
            return "### REDDIT [OFF] \nИнтерфейс отключен."

        return f"### REDDIT [ON] \nНедавняя активность:\n{self.state.recent_activity}"

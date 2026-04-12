from openai import AsyncOpenAI

from src.utils.logger import system_logger
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator


class LLMClient:
    """
    Интерфейс для общения мозга агента с языковой моделью.
    Включает автоматическую ротацию ключей и кэширование HTTP-сессий.
    """

    def __init__(self, api_url: str, api_keys_rotator: APIKeyRotator):
        self.api_url = api_url
        self.rotator = api_keys_rotator

        # Кэш сессий для переиспользования соединений и предотвращения утечек сокетов
        self._sessions: dict[str, AsyncOpenAI] = {}

        # Нормализация URL
        if self.api_url and not self.api_url.startswith(("http://", "https://")):
            if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
                self.api_url = f"http://{self.api_url}"
            else:
                self.api_url = f"https://{self.api_url}"

        if self.api_url:
            system_logger.info(f"[LLM] Клиент инициализирован (URL: {self.api_url}).")
        else:
            system_logger.info("[LLM] Клиент инициализирован (Default OpenAI URL).")

    def get_session(self) -> AsyncOpenAI:
        """
        Возвращает закэшированную сессию OpenAI с актуальным ключом.
        """
        api_key = self.rotator.get_next_key()

        if not api_key:
            raise RuntimeError("[LLM] Нет доступных API ключей. Лимиты исчерпаны.")

        # Ленивая инициализация: создаем клиента только при первом обращении к ключу
        if api_key not in self._sessions:
            self._sessions[api_key] = AsyncOpenAI(api_key=api_key, base_url=self.api_url)

        return self._sessions[api_key]

    async def close(self) -> None:
        """Корректно закрывает все активные пулы HTTP-соединений."""
        for session in self._sessions.values():
            await session.close()

        self._sessions.clear()
        system_logger.info("[LLM] Все HTTP-сессии закрыты.")

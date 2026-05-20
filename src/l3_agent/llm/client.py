"""
Асинхронный клиент для взаимодействия с LLM (OpenAI API совместимый).

Модуль инкапсулирует логику управления HTTP-сессиями и отвечает за бесшовную
интеграцию с любыми провайдерами, поддерживающими стандарт OpenAI
(OpenRouter, Gemini, Anthropic, локальные VLLM и т.д.).
"""

import httpx
from openai import AsyncOpenAI

from src.utils.logger import main_logger
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator


class LLMClient:
    """
    Интерфейс для общения мозга агента с языковой моделью.
    Включает автоматическую ротацию ключей и кэширование HTTP-сессий.
    """

    def __init__(
        self, api_url: str, api_keys_rotator: APIKeyRotator, proxy_url: str = None
    ) -> None:
        """
        Инициализирует клиент.

        Args:
            api_url: Базовый URL для OpenAI API.
            api_keys_rotator: Менеджер API ключей (ротатор).
            proxy_url: URL прокси-сервера.
        """

        self.api_url = api_url
        self.rotator = api_keys_rotator
        self.proxy_url = proxy_url

        self._sessions: dict[str, AsyncOpenAI] = {}

        if self.api_url and not self.api_url.startswith(("http://", "https://")):
            if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
                self.api_url = f"http://{self.api_url}"
            else:
                self.api_url = f"https://{self.api_url}"

        if self.api_url:
            main_logger.info(f"[LLM] Клиент инициализирован (URL: {self.api_url}).")
        else:
            main_logger.info("[LLM] Клиент инициализирован (Default OpenAI URL).")

    def get_session(self) -> AsyncOpenAI:
        """
        Возвращает закэшированную сессию OpenAI с актуальным "живым" ключом.

        Returns:
            Экземпляр AsyncOpenAI, готовый к вызову.

        Raises:
            RuntimeError: Если все API ключи исчерпаны или забанены.
        """

        api_key = self.rotator.get_next_key()

        if not api_key:
            raise RuntimeError("[LLM] Нет доступных API ключей. Лимиты исчерпаны.")

        if api_key not in self._sessions:
            # Настраиваем кастомный HTTP-клиент с поддержкой прокси (в т.ч. SOCKS5)
            http_client = httpx.AsyncClient(proxy=self.proxy_url) if self.proxy_url else None

            self._sessions[api_key] = AsyncOpenAI(
                api_key=api_key,
                base_url=self.api_url if self.api_url else None,
                http_client=http_client,
            )

        return self._sessions[api_key]

    async def close(self) -> None:
        """
        Корректно закрывает все активные пулы HTTP-соединений.
        Вызывается при остановке системы (Graceful Shutdown).
        """
        for session in self._sessions.values():
            await session.close()
        self._sessions.clear()
        main_logger.info("[LLM] Все HTTP-сессии закрыты.")

from openai import AsyncOpenAI

from src.utils.logger import system_logger
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator


class LLMClient:
    """
    Интерфейс для общения мозга агента с языковой моделью.
    Включает автоматическую ротацию ключей и трекинг токенов.
    """

    def __init__(self, api_url: str, api_keys_rotator: APIKeyRotator):
        self.api_url = api_url
        self.rotator = api_keys_rotator

        # Нормализация URL
        if self.api_url and not self.api_url.startswith(("http://", "https://")):
            if "localhost" in self.api_url or "127.0.0.1" in self.api_url:
                self.api_url = f"http://{self.api_url}"
            else:
                self.api_url = f"https://{self.api_url}"

        if self.api_url:
            system_logger.info(
                f"[LLM] Клиент инициализирован (URL: {self.api_url})."
            )
        else:
            system_logger.info("[LLM] Клиент инициализирован (Default OpenAI URL).")

    def get_session(self) -> AsyncOpenAI:
        """
        Генерирует свежую сессию OpenAI с актуальным ключом.
        Использовать так:
        client = await self.llm_client.get_session()
        response = await client.chat.completions.create(...)
        """
        # Просим у ротатора следующий живой ключ
        api_key = self.rotator.get_next_key()

        if not api_key:
            raise RuntimeError("[LLM] Нет доступных API ключей. Лимиты исчерпаны.")

        # Создаем легковесного клиента
        return AsyncOpenAI(api_key=api_key, base_url=self.api_url)

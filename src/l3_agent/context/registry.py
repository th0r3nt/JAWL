import asyncio
from typing import Callable, Awaitable, Any, Dict, List

from src.utils.logger import system_logger


class ContextRegistry:
    """
    Реестр провайдеров контекста.
    Опрашивает зарегистрированные модули и возвращает словарь с их блоками.
    """

    def __init__(self):
        # Хранит пары "имя_модуля" -> асинхронный коллбэк
        self._providers: Dict[str, Callable[..., Awaitable[str]]] = {}

    def register_provider(self, name: str, provider_func: Callable[..., Awaitable[str]]):
        self._providers[name] = provider_func
        system_logger.debug(f"[System] Зарегистрирован провайдер контекста: {name}")

    async def gather_all(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[str], agent_state
    ) -> Dict[str, str]:
        """
        Опрашивает все зарегистрированные модули одновременно.
        Возвращает словарь: {"имя_модуля": "отформатированный Markdown"}.
        """
        if not self._providers:
            return {}

        provider_names = list(self._providers.keys())
        tasks = [
            provider(
                event_name=event_name,
                payload=payload,
                missed_events=missed_events,
                agent_state=agent_state,
            )
            for provider in self._providers.values()
        ]

        # Выполняем параллельно, игнорируя краши отдельных модулей
        results = await asyncio.gather(*tasks, return_exceptions=True)

        context_blocks = {}
        for name, res in zip(provider_names, results):
            if isinstance(res, Exception):
                system_logger.error(
                    f"[System] Ошибка сборки контекста в модуле '{name}': {res}"
                )
                continue

            if res and isinstance(res, str):
                context_blocks[name] = res.strip()

        return context_blocks

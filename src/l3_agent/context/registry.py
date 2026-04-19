import asyncio
from typing import Callable, Awaitable, Any, Dict, List

from src.utils.logger import system_logger


class ContextRegistry:
    """
    Реестр провайдеров контекста.
    Избавляет ContextBuilder от жесткой привязки к интерфейсам и базам данных.
    """

    def __init__(self):
        # Хранит пары "имя_модуля" -> асинхронный коллбэк
        self._providers: Dict[str, Callable[..., Awaitable[str]]] = {}

    def register_provider(self, name: str, provider_func: Callable[..., Awaitable[str]]):
        """
        Регистрирует функцию, которая вернет отформатированную строку контекста.
        Все провайдеры должны принимать **kwargs (event_name, payload, missed_events).
        """

        self._providers[name] = provider_func
        system_logger.debug(f"[System] Зарегистрирован провайдер контекста: {name}")

    async def gather_all(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[str]
    ) -> str:
        """
        Опрашивает все зарегистрированные модули одновременно.
        """

        if not self._providers:
            return ""

        tasks = []
        # Словари в Python сохраняют порядок добавления, так что блоки будут
        # собраны в том порядке, в котором модули были зарегистрированы при старте
        for provider in self._providers.values():
            tasks.append(
                provider(event_name=event_name, payload=payload, missed_events=missed_events)
            )

        # Выполняем параллельно, игнорируя краши отдельных модулей
        results = await asyncio.gather(*tasks, return_exceptions=True)

        context_blocks = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                provider_name = list(self._providers.keys())[i]
                system_logger.error(
                    f"[System] Ошибка сборки контекста в модуле '{provider_name}': {res}"
                )
                continue

            if res and isinstance(res, str):
                context_blocks.append(res.strip())

        return "\n\n\n\n".join(context_blocks)

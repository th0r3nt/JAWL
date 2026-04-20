import asyncio
from typing import Callable, Awaitable, Any, Dict, List

from src.utils.logger import system_logger


class ContextRegistry:
    """
    Реестр провайдеров контекста.
    Опрашивает зарегистрированные модули с учетом их приоритета сортировки
    и возвращает словарь с их блоками.
    """

    def __init__(self):
        # Хранит пары "имя_модуля" -> {"func": коллбэк, "priority": int}
        self._providers: Dict[str, Dict[str, Any]] = {}

    def register_provider(
        self, name: str, provider_func: Callable[..., Awaitable[str]], priority: int = 100
    ):
        self._providers[name] = {"func": provider_func, "priority": priority}
        system_logger.debug(
            f"[System] Зарегистрирован провайдер контекста: {name} (Приоритет: {priority})"
        )

    async def gather_all(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[str], agent_state
    ) -> Dict[str, str]:
        """
        Опрашивает все зарегистрированные модули одновременно.
        Возвращает отсортированный по приоритету словарь: {"имя_модуля": "отформатированный Markdown"}.
        """

        if not self._providers:
            return {}

        # Сортируем ключи по приоритету (по возрастанию)
        sorted_names = sorted(
            self._providers.keys(), key=lambda k: self._providers[k]["priority"]
        )

        tasks = [
            self._providers[name]["func"](
                event_name=event_name,
                payload=payload,
                missed_events=missed_events,
                agent_state=agent_state,
            )
            for name in sorted_names
        ]

        # Выполняем параллельно, игнорируя краши отдельных модулей
        results = await asyncio.gather(*tasks, return_exceptions=True)

        context_blocks = {}
        # Начиная с Python 3.7 dict сохраняет порядок добавления элементов
        for name, res in zip(sorted_names, results):
            if isinstance(res, Exception):
                system_logger.error(
                    f"[System] Ошибка сборки контекста в модуле '{name}': {res}"
                )
                continue

            if res and isinstance(res, str):
                context_blocks[name] = res.strip()

        return context_blocks

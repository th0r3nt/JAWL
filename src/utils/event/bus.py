import asyncio
import inspect
from typing import Any, Callable

from src.utils.event.registry import EventConfig
from src.utils.logger import system_logger


class EventBus:
    def __init__(self):
        self.listeners: dict[str, list[Callable[..., Any]]] = {}
        self.background_tasks: set[asyncio.Task] = set()

    async def _run_handlers(self, tasks: list[Any], event_name: str) -> None:
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                system_logger.error(
                    f"[System] Ошибка в обработчике события '{event_name}': {res}"
                )

    def subscribe(self, event: EventConfig, handler: Callable[..., Any]) -> None:
        """Подписывает функцию на событие."""

        if event.name not in self.listeners:
            self.listeners[event.name] = []

        self.listeners[event.name].append(handler)
        system_logger.debug(f"[System] Подписка: '{handler.__name__}' -> '{event.name}'")

    async def publish(self, event: EventConfig, *args: Any, **kwargs: Any) -> None:
        """Публикует событие."""

        if event.name not in self.listeners:
            system_logger.debug(f"[System] На событие '{event.name}' никто не подписан.")
            return

        handlers = self.listeners[event.name]
        tasks = []

        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                coro = handler(*args, **kwargs)
                tasks.append(coro)
            else:
                tasks.append(asyncio.to_thread(handler, *args, **kwargs))

        if tasks:
            background_task = asyncio.create_task(self._run_handlers(tasks, event.name))
            self.background_tasks.add(background_task)
            background_task.add_done_callback(self.background_tasks.discard)

    def unsubscribe(self, event: EventConfig, handler: Callable[..., Any]) -> None:
        """Отписывает функцию от события."""

        if event.name in self.listeners:
            try:
                self.listeners[event.name].remove(handler)
            except ValueError:
                pass

    async def stop(self) -> None:
        """Ожидает завершения всех фоновых обработчиков событий."""

        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
            self.background_tasks.clear()

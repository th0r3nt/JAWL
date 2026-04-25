import asyncio
from enum import IntEnum
from typing import Callable, Awaitable, Any, Dict, List

from src.utils.logger import system_logger


class ContextSection(IntEnum):
    """
    Определяет строгий порядок следования блоков в системном промпте.
    Чем меньше число, тем выше блок в иерархии.
    """

    # Личность и внутреннее состояние
    DRIVES = 10
    TRAITS = 20
    SKILLS = 30
    AGENT_STATE = 40

    # Универсальный блок для всех L2 интерфейсов
    INTERFACES = 50

    # Базы данных и память
    MENTAL_STATES = 110
    TASKS = 120
    RAG_MEMORIES = 130

    # Последние действия
    RECENT_TICKS = 140

    # Причина пробуждения и фоновые логи
    HEARTBEAT = 150


class ContextRegistry:
    def __init__(self):
        self._providers: Dict[str, Dict[str, Any]] = {}

    def register_provider(
        self, name: str, provider_func: Callable[..., Awaitable[str]], section: ContextSection
    ):
        self._providers[name] = {"func": provider_func, "section": section}
        system_logger.debug(
            f"[System] Зарегистрирован провайдер контекста: {name} (Секция: {section.name})"
        )

    async def gather_all(
        self,
        event_name: str,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        agent_state,
    ) -> Dict[str, str]:
        """
        Проходится по всем провайдерам контекста и дергает их функции,
        которые возвращают отформатированные Markdown-блоки для контекста.
        """

        if not self._providers:
            return {}

        # Сортируем по Enum значению (по возрастанию)
        sorted_names = sorted(
            self._providers.keys(), key=lambda k: self._providers[k]["section"].value
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

        results = await asyncio.gather(*tasks, return_exceptions=True)

        context_blocks = {}
        for name, res in zip(sorted_names, results):
            if isinstance(res, Exception):
                system_logger.error(
                    f"[System] Ошибка сборки контекста в модуле '{name}': {res}"
                )
                continue

            if res and isinstance(res, str):
                context_blocks[name] = res.strip()

        return context_blocks

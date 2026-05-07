# ФАЙЛ: src/l3_agent/subconscious/poller.py
"""
Поллер подсознания.

Следит за течением времени (тиками) и генерирует триггеры для запуска паттернов.
Осуществляет непрерывную синхронизацию состояния счетчиков с L0 State.
"""

from typing import Dict
from src.utils.logger import main_logger, subc_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import SubconsciousConfig
from src.l0_state.agent.state import AgentState
from src.l3_agent.subconscious.schema import Pattern


class SubconsciousPoller:
    """Тихий счетчик тактов. Работает в фоне и будит подсознание по расписанию."""

    def __init__(
        self, agent_state: AgentState, event_bus: EventBus, config: SubconsciousConfig
    ) -> None:
        """
        Инициализирует поллер и сразу синхронизирует лимиты с L0 State.
        """
        self.agent_state = agent_state
        self.bus = event_bus
        self.config = config

        # Храним счетчики: {Pattern.CONSOLIDATION: 0, ...}
        self.counters: Dict[Pattern, int] = {p: 0 for p in Pattern}

        # Первичная инициализация счетчиков в AgentState, чтобы они были видны с первого такта
        self._update_state_counters()

    def _update_state_counters(self) -> None:
        """
        Формирует вложенный словарь со счетчиками лимитов и транслирует его в L0.
        """
        cfg_patterns = self.config.patterns
        limits_map = {
            Pattern.CONSOLIDATION: cfg_patterns.consolidation,
            Pattern.REFLECTION: cfg_patterns.reflection,
            Pattern.FORGETTING: cfg_patterns.forgetting,
        }

        state_counters = {}
        for pattern, p_config in limits_map.items():
            if not p_config.enabled:
                continue
            state_counters[pattern.value] = {
                "current": self.counters[pattern],
                "limit": p_config.activation_limit_ticks,
            }
        self.agent_state.subconscious_counters = state_counters

    async def on_tick_saved(self, **kwargs) -> None:
        """
        Хендлер события REACT_TICK_SAVED.
        Инкрементирует счетчики и пуляет триггеры, если пришло время.
        """

        if not self.config.enabled:
            return

        cfg_patterns = self.config.patterns

        # Конфиг для каждого паттерна
        limits = {
            Pattern.CONSOLIDATION: cfg_patterns.consolidation,
            Pattern.REFLECTION: cfg_patterns.reflection,
            Pattern.FORGETTING: cfg_patterns.forgetting,
        }

        triggered_patterns = []

        for pattern, p_config in limits.items():
            if not p_config.enabled:
                continue

            self.counters[pattern] += 1

            if self.counters[pattern] >= p_config.activation_limit_ticks:
                self.counters[pattern] = 0
                triggered_patterns.append(pattern)

        # Синхронизируем счетчики с L0 State
        self._update_state_counters()

        # Отправляем триггеры в шину событий
        for pattern in triggered_patterns:
            log = f"[Subconscious] Паттерн '{pattern.value}' достиг лимита тиков. Отправка триггера."
            main_logger.info(log)
            subc_logger.info(log)
            
            await self.bus.publish(Events.SUBCONSCIOUS_TRIGGERED, pattern=pattern)

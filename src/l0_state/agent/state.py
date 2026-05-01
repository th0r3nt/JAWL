"""
L0 Стейт (Приборная панель) самого агента.

Хранит жизненные показатели текущего процесса: метаданные ReAct-цикла,
используемую модель LLM, затраты токенов и кратковременную память мыслей
для инъекции в RAG. Эта информация встроена в системный контекст и позволяет
агенту осознавать свою конфигурацию в реальном времени.
"""

import time
from enum import Enum
from pydantic import BaseModel, Field
from src.utils.dtime import seconds_to_duration_str

from src import __version__


class AgentStatus(str, Enum):
    """Текущий статус работы главного агента."""

    IDLE = "idle"  # Ждет следующего тика (находится в сне Heartbeat'а)
    THINKING = "thinking"  # Вычисляет промпт, формирует запрос в LLM или ждет ответа
    ACTING = "acting"  # Выполняет инструменты (execute_skill)
    ERROR = "error"  # Фатальная ошибка в цикле


class AgentState(BaseModel):
    """
    Модель состояния текущего запущенного процесса агента.
    """

    state: AgentStatus = AgentStatus.IDLE

    # Настройки LLM
    llm_model: str = "unknown"
    temperature: float = 0.7

    # ReAct цикл
    current_step: int = 1  # Текущий шаг раздумий в рамкам одного пробуждения
    max_react_steps: int = 15
    heartbeat_interval: int = 180

    # Системные лимиты и режимы
    continuous_cycle: bool = False
    proactive_guidance: bool = False

    context_ticks: int = 15
    context_detailed_ticks: int = 3

    start_time: float = Field(default_factory=time.time)
    last_input_tokens: int = 0

    # Краткосрочная память для ассоциативного RAG и инъекции мультимодальности (изображений)
    last_thoughts: str = ""
    last_action_args: list[str] = Field(default_factory=list)
    last_action_error: str = ""
    last_actions_result: str = ""  # Результат последних выполненных действий

    def reset_step(self) -> None:
        """
        Сбрасывает шаг ReAct-цикла и кратковременную память.
        Вызывается при начале каждого нового пробуждения (тика).
        """
        self.current_step = 1
        self.last_thoughts = ""
        self.last_action_args.clear()
        self.last_action_error = ""
        self.last_actions_result = ""

    def update_state(self, new_state: AgentStatus) -> None:
        """
        Обновляет статус состояния агента (IDLE, THINKING, ACTING, ERROR).

        Args:
            new_state (AgentStatus): Новый статус.
        """
        self.state = new_state

    def next_step(self) -> None:
        """Инкрементирует шаг текущего ReAct-цикла."""
        self.current_step += 1

    def get_uptime(self) -> str:
        """
        Вычисляет аптайм (время работы) текущего инстанса агента.

        Returns:
            str: Человекочитаемая строка формата "DD дней, HH:MM:SS".
        """
        return seconds_to_duration_str(time.time() - self.start_time)

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста.
        Отдает отформатированный Markdown-блок с метаданными агента для инъекции в системный промпт.

        Returns:
            str: Статистика агента, лимиты, версия системы и аптайм.
        """
        
        return f"""
### AGENT STATE
* JAWL Version: {__version__}
* Uptime: {self.get_uptime()}

* Heartbeat Interval: {self.heartbeat_interval}s
* Continuous Cycle: {self.continuous_cycle}
* Context Depth: {self.context_ticks} recent ticks (Detailed: {self.context_detailed_ticks})

* LLM Model: {self.llm_model}
* Temperature: {self.temperature}

* ReAct Step: {self.current_step}/{self.max_react_steps}
* Input Tokens (current step): {self.last_input_tokens}
        """.strip()

import time
from enum import Enum
from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    IDLE = "idle"  # Ждет следующего тика
    THINKING = "thinking"  # Отправил запрос в LLM
    ACTING = "acting"  # Выполняет execute_skill
    ERROR = "error"  # Упал к чертям


class AgentState(BaseModel):
    """
    Текущее состояние агента.
    """

    state: AgentStatus = AgentStatus.IDLE

    # Настройки LLM (заполняются при старте из settings.yaml)
    llm_model: str = "unknown"
    temperature: float = 0.7

    # ReAct цикл
    current_step: int = 1
    max_react_steps: int = 15

    # Время запуска (записывается автоматически при создании объекта)
    start_time: float = Field(default_factory=time.time)

    def update_state(self, new_state: AgentStatus):
        self.state = new_state

    def next_step(self):
        """Увеличивает счетчик шагов в рамках текущего тика."""
        self.current_step += 1

    def reset_step(self):
        """Сбрасывает счетчик в начале нового тика."""
        self.current_step = 1

    def get_uptime(self) -> str:
        """Считает, сколько времени жив сам агент (не ОС хоста)."""
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

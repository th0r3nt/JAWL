import time
from enum import Enum
from pydantic import BaseModel, Field
from src.utils.dtime import seconds_to_duration_str

from src import __version__


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

    # Настройки LLM
    llm_model: str = "unknown"
    temperature: float = 0.7

    # ReAct цикл
    current_step: int = 1  # Хранит текущий шаг раздумий агента
    max_react_steps: int = 15
    heartbeat_interval: int = 180

    # Системные лимиты
    continuous_cycle: bool = False
    proactive_guidance: bool = False

    context_ticks: int = 15
    context_detailed_ticks: int = 3

    start_time: float = Field(default_factory=time.time)
    last_input_tokens: int = 0

    # Краткосрочная память для ассоциативного RAG и инжекта мультимодальности
    last_thoughts: str = ""
    last_action_args: list[str] = Field(default_factory=list)
    last_action_error: str = ""
    last_actions_result: str = ""  # Результат последних выполненных действий

    def reset_step(self):
        self.current_step = 1
        self.last_thoughts = ""
        self.last_action_args.clear()
        self.last_action_error = ""
        self.last_actions_result = ""

    def update_state(self, new_state: AgentStatus):
        self.state = new_state

    def next_step(self):
        self.current_step += 1

    def get_uptime(self) -> str:
        return seconds_to_duration_str(time.time() - self.start_time)

    async def get_context_block(self, **kwargs) -> str:
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

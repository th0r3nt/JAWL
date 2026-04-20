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
    heartbeat_interval: int = 180

    # Аптайм, время первого запуска (записывается автоматически при создании объекта)
    start_time: float = Field(default_factory=time.time)

    # Краткосрочная память для ассоциативного RAG (когда шаг ReAct цикла > 1)
    last_thoughts: str = ""
    last_action_args: list[str] = Field(default_factory=list)
    last_action_error: str = ""
    # По ним будет осуществляться RAG-поиск по базам данных каждый шаг в текущем ReAct-цикле, 
    # чтобы у агента автоматически всплывали воспоминания по своим мыслям/действиям

    def reset_step(self):
        self.current_step = 1
        self.last_thoughts = ""
        self.last_action_args.clear()
        self.last_action_error = ""

    def update_state(self, new_state: AgentStatus):
        self.state = new_state

    def next_step(self):
        """Увеличивает счетчик шагов в рамках текущего тика."""
        self.current_step += 1

    def get_uptime(self) -> str:
        """Считает, сколько времени жив сам агент (не ОС хоста)."""
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # P.S. Функцию сборки контекста засунул сюда, ибо это самое подходящее место
    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Возвращает отформатированный блок для контекста агента.
        """

        return f"""
### AGENT STATE
* Heartbeat Interval: {self.heartbeat_interval}s
* LLM Model: {self.llm_model}
* Temperature: {self.temperature}
* Uptime: {self.get_uptime()}
* ReAct Step: {self.current_step}/{self.max_react_steps}
        """.strip()

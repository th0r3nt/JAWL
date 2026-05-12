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

    # Текущая цель для удержания фокуса при длительных задачах (навык доступен при интерфейсе Meta уровня 0)
    current_goal: str = ""

    # Системные лимиты и режимы
    continuous_cycle: bool = False
    proactive_guidance: bool = False

    context_high_ticks: int = 3
    context_medium_ticks: int = 7
    context_low_ticks: int = 20

    start_time: float = Field(default_factory=time.time)
    last_input_tokens: int = 0

    # Краткосрочная память
    last_thoughts: str = ""
    current_thoughts_tree: str = ""  # Хранит Markdown-дерево мыслей, сгенерированное ToT

    last_action_args: list[str] = Field(default_factory=list)
    last_action_error: str = ""
    last_actions_result: str = ""  # Результат последних выполненных действий

    # Подсознание (Strict nested dictionary typing)
    subconscious_enabled: bool = False
    subconscious_counters: dict[str, dict[str, int]] = Field(default_factory=dict)

    def reset_step(self) -> None:
        """
        Сбрасывает шаг ReAct-цикла и кратковременную память.
        Вызывается при начале каждого нового пробуждения (тика).
        """
        self.current_step = 1
        self.last_thoughts = ""
        self.current_thoughts_tree = ""

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
        Отдает отформатированный Markdown-блок с метаданными агента и подсознания для инъекции в системный промпт.

        Returns:
            str: Статистика агента, лимиты, версия системы, аптайм и состояние подсознания.
        """
        goal_str = (
            f"\n* Current Goal: {self.current_goal}" if self.current_goal else ""
        )

        base_info = f"""
### AGENT STATE
* JAWL Version: {__version__}
* Uptime: {self.get_uptime()}

* Heartbeat Interval: {self.heartbeat_interval}s
* Continuous Cycle: {self.continuous_cycle}
* Context Depth Ticks: High={self.context_high_ticks} | Medium={self.context_medium_ticks} | Low={self.context_low_ticks}

* LLM Model: {self.llm_model}
* Temperature: {self.temperature}

* ReAct Step: {self.current_step}/{self.max_react_steps}
* Input Tokens (current step): {self.last_input_tokens}

{goal_str}

        """.strip()

        # TODO: надо бы этот блок вынести в модуль подсознания, мол "get_context_block" и дергать отсюда
        if self.subconscious_enabled and self.subconscious_counters:
            subc_lines = [
                "\n\n### SUBCONSCIOUS STATE",
                "Когнитивные фоновые процессы, работающие параллельно с основным ReAct-циклом. Они автоматически консолидируют память, адаптируют характер и проводят информационную очистку баз данных.\n",
            ]

            descriptions = {
                "consolidation": "Автоматический перенос краткосрочного операционного опыта (логов действий и мыслей) в долгосрочную семантическую память и структурированные связи. Позволяет кристаллизовать извлеченные факты, правила и знания, предотвращая амнезию.",
                "reflection": "Когнитивная переоценка недавних коммуникаций и паттернов взаимодействия. Обновляет CRM-систему (Mental States) - модулирует отношение (Attitude) к внешним субъектам, фиксирует новые директивы общения и адаптирует характер (Personality Traits).",
                "forgetting": "Информационная гигиена и деградация неактуальных воспоминаний. Сканирует векторную и графовую базы, вычищая битые данные, дубликаты, случайный системный мусор и логи ошибок. Поддерживает высокую семантическую плотность RAG, защищая контекст.",
            }

            for pattern_name, data in sorted(self.subconscious_counters.items()):
                current = data.get("current", 0)
                limit = data.get("limit", 0)
                desc = descriptions.get(pattern_name, "Фоновый когнитивный процесс.")

                display_name = pattern_name.capitalize()

                subc_lines.append(f"* {display_name}")
                subc_lines.append(f"  - until the next launch: {current}/{limit} ticks")
                subc_lines.append(f"  - description: {desc}")

            base_info += "\n".join(subc_lines)

        return base_info

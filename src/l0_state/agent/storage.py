# TODO: сюда складывает текущее состояние слой agent/: текущий статус мозга (think, sleep) и прочее
# Важно: этот файл является строго пассивным хранилищем: сам он ничего не делает, а лишь хранить данные для агента

from enum import Enum
from pydantic import BaseModel

class AgentStatus(str, Enum):
    IDLE = "idle"             # Ждет следующего тика
    THINKING = "thinking"     # Отправил запрос в LLM
    ACTING = "acting"         # Выполняет execute_skill
    SLEEPING = "sleeping"     # Принудительный таймаут
    ERROR = "error"           # Упал, нужна самодиагностика

class AgentState(BaseModel):
    """
    Текущее состояние агента.
    Только хранит данные.
    """
    status: AgentStatus = AgentStatus.IDLE
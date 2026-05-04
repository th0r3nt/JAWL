import time
from src.l0_state.agent.state import AgentState, AgentStatus


def test_agent_state_defaults():
    """Тест: дефолтные значения при инициализации."""
    state = AgentState()
    assert state.state == AgentStatus.IDLE
    assert state.current_step == 1
    assert state.max_react_steps == 15


def test_agent_state_transitions():
    """Тест: мутации стейта и шагов ReAct-цикла."""
    state = AgentState()

    state.update_state(AgentStatus.THINKING)
    assert state.state == AgentStatus.THINKING

    state.next_step()
    assert state.current_step == 2

    state.reset_step()
    assert state.current_step == 1


def test_agent_uptime(monkeypatch):
    """Тест: форматирование времени жизни агента."""
    state = AgentState()

    # Мокаем time.time(), чтобы "перемотать" время на 1 час, 1 минуту и 5 секунд вперед
    original_time = time.time
    monkeypatch.setattr(time, "time", lambda: original_time() + 3665)

    uptime = state.get_uptime()
    assert uptime == "01:01:05"

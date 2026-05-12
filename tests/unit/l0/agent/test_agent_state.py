import time
from src.l0_state.agent.state import AgentState, AgentStatus
import pytest


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


@pytest.mark.asyncio
async def test_agent_state_context_block_no_subconscious():
    """Тест: Если подсознание отключено, блок не выводится в системный промпт."""
    state = AgentState()
    state.subconscious_enabled = False

    block = await state.get_context_block()
    assert "SUBCONSCIOUS STATE" not in block


@pytest.mark.asyncio
async def test_agent_state_context_block_with_subconscious():
    """Тест: Динамический рендер счетчиков паттернов подсознания."""
    state = AgentState()
    state.subconscious_enabled = True

    # Имитируем данные, которые передает SubconsciousPoller
    state.subconscious_counters = {
        "consolidation": {"current": 12, "limit": 30},
        "forgetting": {"current": 5, "limit": 90},
    }

    block = await state.get_context_block()

    assert "SUBCONSCIOUS STATE" in block
    assert "Consolidation" in block
    assert "12/30 ticks" in block

    assert "Forgetting" in block
    assert "5/90 ticks" in block

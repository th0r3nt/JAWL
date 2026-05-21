import pytest

from src.l2_interfaces.telegram.aiogram.state import AiogramState
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.terminal.state import HostTerminalState
from src.l2_interfaces.web.search.state import WebSearchState
from src.l2_interfaces.calendar.state import CalendarState
from src.l2_interfaces.meta.state import CustomDashboardState


def test_host_terminal_state_init():
    state = HostTerminalState(context_limit=10)
    assert state.context_limit == 10
    assert state.recent_messages == []
    assert state.formatted_messages == "Message history is empty."


def test_aiogram_state_init():
    state = AiogramState()
    assert state.last_chats == "Dialogues list is empty."
    assert state._chats_cache == {}


def test_host_os_state_init():
    state = HostOSState()
    assert state.uptime == "Unknown."
    assert state.sandbox_files == "Unknown."
    assert state.telemetry == "No available telemetry."


def test_calendar_state_init():
    """Test: default calendar state initialization."""
    state = CalendarState()
    assert state.is_online is False
    assert state.upcoming_events == "No events."


def test_web_search_state_mru():
    state = WebSearchState(history_limit=2)

    state.add_history("site_A")
    state.add_history("site_B")
    state.add_history("site_C")

    assert len(state.history) == 2
    assert state.history == ["site_C", "site_B"]

    assert "site_C" in state.browser_history
    assert "site_A" not in state.browser_history


@pytest.mark.asyncio
async def test_custom_dashboard_state_formatting():
    state = CustomDashboardState()

    assert await state.get_context_block() == ""

    state.blocks["Crypto"] = "BTC: $100k"
    state.blocks["Weather"] = "Sunny, +25C"

    block = await state.get_context_block()

    assert "### CUSTOM: Crypto" in block
    assert "BTC: $100k" in block
    assert "### CUSTOM: Weather" in block
    assert "Sunny, +25C" in block

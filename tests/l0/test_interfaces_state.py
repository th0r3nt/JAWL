from src.l0_state.interfaces.state import (
    TelethonState,
    AiogramState,
    HostOSState,
    HostTerminalState,
    WebSearchState,
    CalendarState,
)


def test_telethon_state_init():
    state = TelethonState(number_of_last_chats=5)
    assert state.number_of_last_chats == 5
    assert state.last_chats == ""


def test_aiogram_state_init():
    state = AiogramState()
    assert state.last_chats == "Список диалогов пуст."
    assert state._chats_cache == {}


def test_host_os_state_init():
    state = HostOSState()
    assert state.uptime == ""
    assert state.sandbox_files == ""
    assert state.telemetry == ""


def test_host_terminal_state_init():
    state = HostTerminalState(number_of_last_messages=10)
    assert state.number_of_last_messages == 10
    assert state.messages == ""


def test_calendar_state_init():
    """Тест: Дефолтная инициализация стейта календаря."""
    state = CalendarState()
    assert state.is_online is False
    assert state.upcoming_events == "Событий нет."


def test_web_search_state_mru():
    """Тест: WebSearchState вытесняет старые записи при превышении лимита (MRU Cache)."""
    state = WebSearchState(history_limit=2)

    state.add_history("site_A")
    state.add_history("site_B")
    state.add_history("site_C")  # Должен вытеснить site_A

    assert len(state.history) == 2
    assert state.history == ["site_C", "site_B"]

    assert "site_C" in state.browser_history
    assert "site_A" not in state.browser_history

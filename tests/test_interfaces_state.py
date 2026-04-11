from src.l0_state.interfaces.state import (
    TelethonState,
    AiogramState,
    HostOSState,
    HostTerminalState,
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

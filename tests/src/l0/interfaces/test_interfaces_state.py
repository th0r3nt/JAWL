import pytest

from src.l0_state.interfaces.state import (
    AiogramState,
    HostOSState,
    HostTerminalState,
    WebSearchState,
    CalendarState,
    CustomDashboardState,
)


def test_host_terminal_state_init():
    state = HostTerminalState(context_limit=10)
    assert state.context_limit == 10
    assert state.recent_messages == []
    assert state.formatted_messages == "История сообщений пуста."


def test_aiogram_state_init():
    state = AiogramState()
    assert state.last_chats == "Список диалогов пуст."
    assert state._chats_cache == {}


def test_host_os_state_init():
    state = HostOSState()
    assert state.uptime == ""
    assert state.sandbox_files == ""
    assert state.telemetry == ""


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


@pytest.mark.asyncio
async def test_custom_dashboard_state_formatting():
    """Тест: CustomDashboardState корректно форматирует блоки в Markdown."""
    state = CustomDashboardState()

    # 1. Пустой стейт должен возвращать пустую строку
    assert await state.get_context_block() == ""

    # 2. Добавляем данные
    state.blocks["Crypto"] = "BTC: $100k"
    state.blocks["Weather"] = "Sunny, +25C"

    block = await state.get_context_block()

    # 3. Проверяем форматирование
    assert "### CUSTOM: Crypto" in block
    assert "BTC: $100k" in block
    assert "### CUSTOM: Weather" in block
    assert "Sunny, +25C" in block

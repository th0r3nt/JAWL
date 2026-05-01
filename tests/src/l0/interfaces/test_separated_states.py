"""
Unit-тесты логики для разбитых файлов состояния (L0 State).

Проверяют, что MRU-кэши (Most Recently Used) в пассивных стейтах интерфейсов
корректно ограничивают свою длину и обрезают старые записи (чтобы контекст не переполнялся).
"""

from src.l0_state.interfaces.github_state import GithubState
from src.l0_state.interfaces.web.browser_state import WebBrowserState
from src.l0_state.interfaces.web.http_state import WebHTTPState
from src.l0_state.interfaces.web.search_state import WebSearchState


def test_github_state_history_limits() -> None:
    """Тест: GithubState корректно сдвигает MRU-кэш истории вызовов API."""
    state = GithubState(history_limit=2)

    state.add_history("Action 1")
    state.add_history("Action 2")
    state.add_history("Action 3")  # Вытеснит "Action 1"

    # Новые элементы добавляются в начало (индекс 0)
    assert len(state.history) == 2
    assert state.history[0] == "Action 3"
    assert state.history[1] == "Action 2"

    assert "Action 1" not in state.github_history
    assert "- Action 3" in state.github_history


def test_github_state_watcher_events_limits() -> None:
    """Тест: Кэш событий Watcher-ов GitHub не превышает захардкоженный лимит (10)."""
    state = GithubState()

    # Запихиваем 15 событий
    for i in range(15):
        state.add_watcher_event(f"Event {i}")

    assert len(state.recent_watcher_events) == 10
    # Событие 14 должно быть первым, а самые старые (0, 1, 2, 3, 4) вытеснены
    assert state.recent_watcher_events[0] == "Event 14"
    assert "Event 0" not in state.recent_watcher_events


def test_browser_state_history_limits() -> None:
    """Тест: WebBrowserState обрезает историю навигации браузера."""
    state = WebBrowserState()

    for i in range(15):
        state.add_history(f"URL {i}")

    # В коде браузера захардкожен лимит в 10 записей
    assert len(state.history) == 10
    assert state.history[0] == "URL 14"


def test_http_state_history_limits() -> None:
    """Тест: WebHTTPState корректно обрезает историю REST-вызовов."""
    state = WebHTTPState(history_limit=3)

    for i in range(5):
        state.add_history(f"GET /endpoint/{i}")

    assert len(state.history) == 3
    assert state.history[0] == "GET /endpoint/4"

    formatted = state.http_history
    assert "- GET /endpoint/4" in formatted
    assert "GET /endpoint/0" not in formatted


def test_search_state_history_limits() -> None:
    """Тест: WebSearchState работает корректно."""
    state = WebSearchState(history_limit=2)

    state.add_history("Search A")
    state.add_history("Search B")
    state.add_history("Search C")

    assert len(state.history) == 2
    assert state.history[0] == "Search C"

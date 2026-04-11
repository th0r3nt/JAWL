import pytest
from src.utils.token_tracker import TokenTracker


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def tracker():
    """Создает свежий трекер с небольшим лимитом для тестов."""
    return TokenTracker(maxlen=3)


# ===================================================================
# TESTS
# ===================================================================


def test_add_input_record(tracker):
    """Тест: правильный подсчет токенов для prompt и context."""
    # 16 символов = 4 токена
    prompt = "a" * 16
    # 8 символов = 2 токена
    context = "b" * 8

    msg = tracker.add_input_record(prompt, context)

    assert len(tracker.input_history) == 1
    assert tracker.input_history[0] == {"prompt": 4, "context": 2, "total": 6}
    assert "Input tokens: 6" in msg
    assert "prompt: 4" in msg
    assert "context: 2" in msg


def test_add_output_record(tracker):
    """Тест: правильный подсчет исходящих токенов."""
    # 20 символов = 5 токенов
    output = "c" * 20

    msg = tracker.add_output_record(output)

    assert len(tracker.output_history) == 1
    assert tracker.output_history[0] == {"total": 5}
    assert "Output tokens: 5" in msg


def test_get_token_statistics_empty(tracker):
    """Тест: возврат заглушки, если история пуста."""
    stats = tracker.get_token_statistics()

    assert "Input: No data yet." in stats
    assert "Output: No data yet." in stats


def test_get_token_statistics_populated(tracker):
    """Тест: правильный подсчет средних значений и суммы."""
    # Вход: 4 (1т) + 8 (2т) = 3т. Сумма = 3
    tracker.add_input_record("a" * 4, "b" * 8)
    # Вход: 8 (2т) + 12 (3т) = 5т. Общая сумма = 8. Среднее = 4
    tracker.add_input_record("a" * 8, "b" * 12)

    # Выход: 4 (1т). Сумма = 1
    tracker.add_output_record("c" * 4)
    # Выход: 12 (3т). Общая сумма = 4. Среднее = 2
    tracker.add_output_record("c" * 12)

    stats = tracker.get_token_statistics()

    assert "8 входных токенов" in stats
    assert "в среднем 4/вызов" in stats
    assert "4 выходных токенов" in stats
    assert "в среднем 2/вызов" in stats


def test_tracker_maxlen(tracker):
    """Тест: старые записи должны удаляться при превышении maxlen."""
    # У нашего трекера maxlen=3. Запишем 5 элементов.
    for _ in range(5):
        tracker.add_output_record("a" * 4)  # 1 токен

    assert len(tracker.output_history) == 3

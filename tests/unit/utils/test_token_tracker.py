import pytest
from src.utils.token_tracker import TokenTracker


@pytest.fixture
def tracker():
    return TokenTracker(maxlen=3)


def test_add_input_record(tracker):
    prompt = "test prompt " * 10
    context = "test context " * 10

    tracker.add_input_record([prompt, context])

    assert len(tracker.input_history) == 1
    assert tracker.input_history[0]["total"] > 0


def test_add_output_record(tracker):
    output = "test output " * 10
    tracker.add_output_record(output)

    assert len(tracker.output_history) == 1
    assert tracker.output_history[0]["total"] > 0


def test_tracker_maxlen(tracker):
    for _ in range(5):
        tracker.add_output_record("test")
    assert len(tracker.output_history) == 3

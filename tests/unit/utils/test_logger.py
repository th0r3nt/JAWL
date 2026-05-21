import logging
from src.utils.logger import ColorFormatter, LogColors, update_log_level, main_logger


def test_color_formatter_truncation_for_console():
    """Test: long console messages are truncated to protect stdout buffer."""
    formatter = ColorFormatter(max_console_length=50)

    long_message = "A" * 100
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=f"[Agent Action Result] {long_message}",
        args=(),
        exc_info=None,
    )

    formatted_str = formatter.format(record)

    assert len(formatted_str) < 150
    assert "Output truncated for terminal" in formatted_str

    assert record.msg == f"[Agent Action Result] {long_message}"


def test_color_formatter_coloring():
    """Test: Prefix coloring."""
    formatter = ColorFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="[Thoughts] Thinking about eternity",
        args=(),
        exc_info=None,
    )
    formatted_str = formatter.format(record)

    assert LogColors.MAGENTA in formatted_str
    assert LogColors.RESET in formatted_str


def test_update_log_level():
    update_log_level("DEBUG")
    assert main_logger.level == logging.DEBUG
    update_log_level("INFO")

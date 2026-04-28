from src.cli.screens.logs import _colorize_log_line, _current_log_color  # noqa: F401
import src.cli.screens.logs as logs_module

def test_colorize_log_line():
    """Тест: раскраска логов для консоли налету."""
    logs_module._current_log_color = ""
    
    txt1 = _colorize_log_line("2024-05-05 - [Heartbeat] Пробуждение")
    assert "bright_magenta" in str(txt1.spans)
    
    txt2 = _colorize_log_line("Это продолжение мысли с предыдущей строки")
    assert "bright_magenta" in str(txt2.spans)
    
    txt3 = _colorize_log_line("2024-05-05 - SYSTEM - ERROR - Всё сломалось")
    assert "bold red" in str(txt3.spans)
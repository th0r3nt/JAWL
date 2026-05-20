import pytest
from unittest.mock import patch, MagicMock

from src.cli.screens.agent_control import (
    _is_agent_running,
    _check_and_setup_prompts,
)


@patch("src.cli.screens.agent_control.is_agent_running")
def test_is_agent_running_proxy(mock_global_is_running):
    """Тест: локальная функция просто проксирует вызов в утилиты."""
    mock_global_is_running.return_value = True
    assert _is_agent_running() is True
    mock_global_is_running.assert_called_once()


@patch("src.cli.screens.agent_control.PROMPTS_DIR")
def test_check_and_setup_prompts(mock_prompts_dir, tmp_path):
    """Тест: копирование файлов личности из шаблонов."""
    test_dir = tmp_path / "prompts"
    test_dir.mkdir()
    (test_dir / "SOUL.example.md").touch()

    mock_prompts_dir.exists.return_value = True
    mock_prompts_dir.rglob.return_value = [test_dir / "SOUL.example.md"]

    with patch("src.cli.screens.agent_control.shutil.copy") as mock_copy:
        _check_and_setup_prompts()
        mock_copy.assert_called_once()
        assert "SOUL.md" in str(mock_copy.call_args[0][1])

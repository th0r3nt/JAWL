import psutil
from unittest.mock import patch, MagicMock

from src.cli.screens.agent_control import (
    _is_agent_running,
    _check_and_setup_prompts,
)


@patch("src.cli.screens.agent_control.psutil.Process")
@patch("src.cli.screens.agent_control.psutil.pid_exists")
@patch("src.cli.screens.agent_control.get_pid_file_path")
def test_is_agent_running_true(mock_get_pid, mock_pid_exists, mock_process):
    """Тест: _is_agent_running определяет запущенного агента."""
    mock_file = MagicMock()
    mock_file.exists.return_value = True
    mock_file.read_text.return_value = "1234"
    mock_get_pid.return_value = mock_file

    mock_pid_exists.return_value = True
    mock_proc = MagicMock()
    mock_proc.is_running.return_value = True
    mock_proc.name.return_value = "python.exe"
    mock_process.return_value = mock_proc

    assert _is_agent_running() is True


@patch("src.cli.screens.agent_control.psutil.Process")
@patch("src.cli.screens.agent_control.psutil.pid_exists")
@patch("src.cli.screens.agent_control.get_pid_file_path")
def test_is_agent_running_zombie(mock_get_pid, mock_pid_exists, mock_process):
    """Тест: процесс не существует (NoSuchProcess). Файл должен быть удален."""
    mock_file = MagicMock()
    mock_file.exists.return_value = True
    mock_file.read_text.return_value = "1234"
    mock_get_pid.return_value = mock_file

    mock_pid_exists.return_value = True
    mock_process.side_effect = psutil.NoSuchProcess(pid=1234)

    assert _is_agent_running() is False
    mock_file.unlink.assert_called_once()


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

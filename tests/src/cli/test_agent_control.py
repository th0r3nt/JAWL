import psutil
from unittest.mock import patch, MagicMock

from src.cli.screens.agent_control import (
    _is_agent_running,
    _check_and_setup_env,
    _check_and_setup_prompts,
)


# Патчим только функции, а не весь psutil
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

    # Теперь исключение выбросится корректно
    mock_process.side_effect = psutil.NoSuchProcess(pid=1234)

    assert _is_agent_running() is False
    mock_file.unlink.assert_called_once()


@patch("src.cli.screens.agent_control.ENV_FILE")
@patch("src.cli.screens.agent_control.questionary")
def test_check_and_setup_env_interactive(mock_questionary, mock_env_file, tmp_path):
    """Тест: интерактивный запрос API ключа, если его нет в .env."""
    test_env = tmp_path / ".env"
    test_env.write_text('LLM_API_KEY_1=""\nLLM_API_URL=""\n', encoding="utf-8")

    mock_env_file.exists.return_value = True
    mock_env_file.__fspath__ = MagicMock(return_value=str(test_env))
    mock_env_file.open = test_env.open

    mock_url_ask = MagicMock()
    mock_url_ask.ask.return_value = "http://local:8000"

    mock_key_ask = MagicMock()
    mock_key_ask.ask.return_value = "sk-12345"

    mock_questionary.text.side_effect = [mock_url_ask, mock_key_ask]

    with patch("src.cli.screens.agent_control.ENV_FILE", test_env):
        success, modified = _check_and_setup_env()

    assert success is True
    assert modified is True

    content = test_env.read_text(encoding="utf-8")
    assert 'LLM_API_KEY_1="sk-12345"' in content
    assert 'LLM_API_URL="http://local:8000"' in content


@patch("src.cli.screens.agent_control.PROMPTS_DIR")
def test_check_and_setup_prompts(mock_prompts_dir, tmp_path):
    """Тест: копирование файлов личности из шаблонов."""
    test_dir = tmp_path / "prompts"
    test_dir.mkdir()
    (test_dir / "SOUL.example.md").touch()

    mock_prompts_dir.exists.return_value = True
    mock_prompts_dir.rglob.return_value = [test_dir / "SOUL.example.md"]

    with patch("src.cli.screens.agent_control.shutil.copy") as mock_copy:
        created = _check_and_setup_prompts()

        assert created is True
        mock_copy.assert_called_once()
        assert "SOUL.md" in str(mock_copy.call_args[0][1])

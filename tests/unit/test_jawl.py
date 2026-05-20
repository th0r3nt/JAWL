import os
import pytest
from unittest.mock import patch, MagicMock

import jawl


def test_is_venv():
    """Тест: определение виртуального окружения."""
    with patch("sys.prefix", "venv_path"), patch("sys.base_prefix", "global_path"):
        assert jawl.is_venv() is True

    with patch("sys.prefix", "global_path"), patch("sys.base_prefix", "global_path"):
        assert jawl.is_venv() is False


def test_recover_deploy_crashes(tmp_path):
    """Тест: механизм воскрешения из пепла (интеграционный тест на tmp_path)."""
    root_dir = tmp_path

    backup_dir = root_dir / "src" / "utils" / "local" / "data" / "deploy_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Активируем сессию
    (backup_dir / ".deploy_active").touch()

    # Создаем бэкап старого файла
    old_file = backup_dir / "main.py"
    old_file.write_text("print('old code')", encoding="utf-8")

    # Создаем манифест с добавленным новым файлом
    manifest = backup_dir / ".newfiles_manifest"
    manifest.write_text("src/new_script.py\n", encoding="utf-8")

    # Создаем рабочую директорию, как будто агент туда написал
    src_dir = root_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    main_file = root_dir / "main.py"
    main_file.write_text("print('broken new code')", encoding="utf-8")

    new_script = src_dir / "new_script.py"
    new_script.touch()

    # Вызываем функцию восстановления
    jawl.recover_deploy_crashes(root_dir)

    # Проверки:
    assert main_file.read_text(encoding="utf-8") == "print('old code')"
    assert not new_script.exists()
    assert not backup_dir.exists()

    events_dir = root_dir / "sandbox" / ".jawl_events"
    assert events_dir.exists()
    events = list(events_dir.glob("*.json"))
    assert len(events) == 1
    assert "Критический сбой" in events[0].read_text(encoding="utf-8")


@patch("sys.argv", ["jawl.py", "--version"])
@patch("jawl.subprocess.call", return_value=0)
@patch("jawl.venv.create")
@patch("jawl.is_venv", return_value=False)
@patch("jawl.recover_deploy_crashes")  # Изолируем, чтобы не ломала моки
def test_setup_and_run_classic_pip_success(
    mock_recover, mock_is_venv, mock_create, mock_call, tmp_path
):
    """
    Happy Path: стандартный `pip install -r requirements.txt` проходит успешно.
    uv не привлекается, юзеру вопросы не задаются.
    """

    with patch("jawl.Path") as mock_path, patch("jawl.subprocess.run") as mock_run, patch(
        "builtins.input"
    ) as mock_input:

        # Настройка виртуальной файловой системы для мока
        mock_root = MagicMock()
        mock_path.return_value.resolve.return_value.parent = mock_root

        mock_venv_dir = MagicMock()
        mock_venv_dir.exists.return_value = False
        mock_req_file = MagicMock()
        mock_req_file.exists.return_value = True

        def side_effect_div(name):
            if name == "venv":
                return mock_venv_dir
            if name == "requirements.txt":
                return mock_req_file
            return MagicMock()

        mock_root.__truediv__.side_effect = side_effect_div

        # Мокаем успешное выполнение subprocess.run (returncode = 0)
        mock_run.return_value = MagicMock(returncode=0)

        with patch("sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit
            with pytest.raises(SystemExit):
                jawl.setup_and_run()

        # pip install и pip upgrade вызвались, вопросов к юзеру не было
        assert mock_run.call_count == 2
        mock_input.assert_not_called()


@patch("sys.argv", ["jawl.py", "--version"])
@patch("jawl.subprocess.call", return_value=0)
@patch("jawl.venv.create")
@patch("jawl.shutil.rmtree")
@patch("jawl.is_venv", return_value=False)
@patch("jawl.recover_deploy_crashes")  # Изолируем
def test_setup_and_run_uv_fallback_accepted(
    mock_recover, mock_is_venv, mock_rmtree, mock_create, mock_call, tmp_path
):
    """
    Edge Case 1: pip install падает (например на Python 3.13),
    юзер соглашается (вводит 'y') на установку uv.
    """

    with patch("jawl.Path") as mock_path, patch("jawl.subprocess.run") as mock_run, patch(
        "builtins.input", return_value="y"
    ) as mock_input:

        mock_root = MagicMock()
        mock_path.return_value.resolve.return_value.parent = mock_root

        mock_venv_dir = MagicMock()
        mock_venv_dir.exists.return_value = False
        mock_req_file = MagicMock()
        mock_req_file.exists.return_value = True

        mock_root.__truediv__.side_effect = lambda n: (
            mock_venv_dir if n == "venv" else mock_req_file
        )

        # Динамически возвращаем returncode=1 только для классического pip install -r
        def mock_run_behavior(args, **kwargs):
            if "install" in args and "-r" in args and "uv" not in args:
                return MagicMock(returncode=1)  # ОШИБКА
            return MagicMock(returncode=0)  # УСПЕХ для всего остального (uv venv, uv pip)

        mock_run.side_effect = mock_run_behavior

        with patch("sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit
            with pytest.raises(SystemExit):
                jawl.setup_and_run()

        # Убеждаемся, что диалог с пользователем был
        mock_input.assert_called_once()

        # Проверяем последовательность команд восстановления
        calls = mock_run.call_args_list
        assert any("uv" in c[0][0] and "install" in c[0][0] for c in calls)  # pip install uv
        assert any(
            "uv" in c[0][0] and "venv" in c[0][0] and "--python" in c[0][0] for c in calls
        )  # uv venv --python 3.11

        # Проверяем, что битый venv был удален
        mock_rmtree.assert_called_once_with(mock_venv_dir, ignore_errors=True)


@patch("sys.argv", ["jawl.py", "--version"])
@patch("jawl.subprocess.call", return_value=0)
@patch("jawl.venv.create")
@patch("jawl.is_venv", return_value=False)
@patch("jawl.recover_deploy_crashes")  # Изолируем
def test_setup_and_run_uv_fallback_rejected(
    mock_recover, mock_is_venv, mock_create, mock_call, tmp_path
):
    """
    Edge Case 2: pip install падает, но юзер отказывается от uv (вводит 'n').
    Скрипт должен корректно завершиться (sys.exit(1)).
    """
    
    with patch("jawl.Path") as mock_path, patch("jawl.subprocess.run") as mock_run, patch(
        "builtins.input", return_value="n"
    ):

        mock_root = MagicMock()
        mock_path.return_value.resolve.return_value.parent = mock_root

        mock_venv_dir = MagicMock()
        mock_venv_dir.exists.return_value = False
        mock_req_file = MagicMock()
        mock_req_file.exists.return_value = True

        mock_root.__truediv__.side_effect = lambda n: (
            mock_venv_dir if n == "venv" else mock_req_file
        )

        def mock_run_behavior(args, **kwargs):
            if "install" in args and "-r" in args:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        mock_run.side_effect = mock_run_behavior

        with patch("sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit
            with pytest.raises(SystemExit):
                jawl.setup_and_run()

            mock_exit.assert_called_with(1)


@patch("sys.argv", ["jawl.py", "--version"])
@patch("jawl.subprocess.call", return_value=0)
@patch("jawl.is_venv", return_value=False)
@patch("jawl.recover_deploy_crashes")  # Изолируем
def test_setup_and_run_environment_isolation(mock_recover, mock_is_venv, mock_call, tmp_path):
    """
    Security/Stability Test: Проверяем, что перед запуском дочернего процесса
    будут жестко вырезаны переменные PYTHONPATH и PYTHONHOME.
    """

    os.environ["PYTHONPATH"] = "/path/to/some/python3.13/libs"
    os.environ["PYTHONHOME"] = "/path/to/python"

    with patch("jawl.Path") as mock_path, patch("jawl.subprocess.run") as mock_run:  # noqa: F841

        # Симулируем, что venv уже установлен
        mock_venv_dir = MagicMock()
        mock_venv_dir.exists.return_value = True
        mock_path.return_value.resolve.return_value.parent.__truediv__.return_value = (
            mock_venv_dir
        )

        with patch("sys.exit") as mock_exit:
            mock_exit.side_effect = SystemExit
            with pytest.raises(SystemExit):
                jawl.setup_and_run()

        # Проверяем аргументы вызова subprocess.call (где запускается сам агент)
        call_kwargs = mock_call.call_args[1]
        passed_env = call_kwargs.get("env", {})

        assert "PYTHONPATH" not in passed_env
        assert "PYTHONHOME" not in passed_env

    # Подчищаем глобальный os.environ после теста
    del os.environ["PYTHONPATH"]
    del os.environ["PYTHONHOME"]

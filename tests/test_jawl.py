import pytest
from unittest.mock import patch, MagicMock

import jawl


def test_is_venv():
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
    # 1. Файл main.py должен был откатиться к бэкапу
    assert main_file.read_text(encoding="utf-8") == "print('old code')"

    # 2. Файл new_script.py должен быть удален
    assert not new_script.exists()

    # 3. Директория бэкапа должна быть удалена
    assert not backup_dir.exists()

    # 4. В песочнице должен лежать вебхук с ошибкой
    events_dir = root_dir / "sandbox" / ".jawl_events"
    assert events_dir.exists()
    events = list(events_dir.glob("*.json"))
    assert len(events) == 1
    assert "Критический сбой" in events[0].read_text(encoding="utf-8")


@patch("sys.argv", ["jawl.py", "--version"])
@patch("jawl.subprocess.run")
@patch("jawl.subprocess.call")
@patch("jawl.venv.create")
@patch("jawl.is_venv", return_value=False)
def test_setup_and_run_outside_venv(mock_is_venv, mock_create, mock_call, mock_run, tmp_path):
    """Тест: запуск вне venv должен создать окружение и дергнуть subprocess."""
    with patch("jawl.Path") as mock_path:
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

        mock_run.return_value.returncode = 0
        mock_call.return_value = 0

        with patch("sys.exit") as mock_exit:
            # ФИКС: Делаем так, чтобы замоканный sys.exit реально прерывал выполнение
            mock_exit.side_effect = SystemExit

            with pytest.raises(SystemExit):
                jawl.setup_and_run()

            mock_create.assert_called_once()
            mock_run.assert_called_once()
            mock_call.assert_called_once()
            mock_exit.assert_called_once_with(0)

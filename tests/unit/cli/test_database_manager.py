from pathlib import Path
from unittest.mock import patch
from src.cli.screens.database_manager import _get_sql_stats, _clear_sandbox


@patch("src.cli.screens.database_manager._run_sql")
@patch("src.cli.screens.database_manager.SQL_DB_FILE")
def test_get_sql_stats(mock_db_file, mock_run_sql):
    """Тест: менеджер БД корректно собирает статистику."""
    mock_db_file.exists.return_value = True

    mock_run_sql.side_effect = [
        (5,),  # tasks
        (2,),  # traits
        (8,),  # mental_states
        [("fundamental", 3), ("custom", 4)],  # drives
    ]

    stats = _get_sql_stats()

    assert stats["tasks"] == 5
    assert stats["personality_traits"] == 2
    assert stats["mental_states"] == 8
    assert stats["drives_fund"] == 3
    assert stats["drives_cust"] == 4


def test_clear_sandbox_wipes_user_files_and_restores_structure(tmp_path: Path):
    """Тест: _clear_sandbox полностью удаляет пользовательские файлы, но восстанавливает _system."""
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True)

    # Создаем пользовательские файлы
    (sandbox_dir / "user_script.py").write_text("print(1)", encoding="utf-8")
    user_folder = sandbox_dir / "my_project"
    user_folder.mkdir()
    (user_folder / "file.txt").write_text("secret", encoding="utf-8")

    # Создаем структуру шаблона
    templates_dir = tmp_path / "src" / "utils" / "templates"
    templates_dir.mkdir(parents=True)
    (templates_dir / "framework_api.py").write_text("# API Template", encoding="utf-8")

    with patch("src.cli.screens.database_manager.SANDBOX_DIR", sandbox_dir), patch(
        "src.cli.screens.database_manager.ROOT_DIR", tmp_path
    ):
        _clear_sandbox()

    # Пользовательские файлы и папки должны исчезнуть
    assert not (sandbox_dir / "user_script.py").exists()
    assert not user_folder.exists()

    # Системная папка и API должны быть восстановлены
    assert (sandbox_dir / "_system" / "download").exists()
    assert (sandbox_dir / "_system" / ".jawl_events").exists()
    assert (sandbox_dir / "_system" / "framework_api.py").exists()
    assert (sandbox_dir / "_system" / "framework_api.py").read_text() == "# API Template"

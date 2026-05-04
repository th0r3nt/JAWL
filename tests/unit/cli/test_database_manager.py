from unittest.mock import patch
from src.cli.screens.database_manager import _get_sql_stats


@patch("src.cli.screens.database_manager._run_sql")
@patch("src.cli.screens.database_manager.SQL_DB_FILE")
def test_get_sql_stats(mock_db_file, mock_run_sql):
    """Тест: менеджер БД корректно собирает статистику."""
    mock_db_file.exists.return_value = True

    # Имитируем ответы от SQLite (3 таблицы COUNT + 1 GROUP BY для Drives)
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

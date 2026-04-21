"""
Экран для сброса памяти агента (БД).
Позволяет физически удалить локальные файлы БД (SQLite и Vector).
Безопасно работает только при выключенном агенте.
"""

import shutil
import sqlite3
from pathlib import Path
import questionary
from qdrant_client import QdrantClient  # <-- Добавили импорт

from src.cli.widgets.ui import (
    draw_header,
    get_custom_style,
    print_error,
    print_info,
    print_success,
    wait_for_enter,
)
from src.cli.screens.agent_control import _is_agent_running

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_DIR = ROOT_DIR / "src" / "utils" / "local" / "data"

SQL_DB_FILE = DB_DIR / "sql_db" / "agent.db"
VECTOR_DB_DIR = DB_DIR / "vector_db"


def _get_sql_stats() -> dict[str, int]:
    """Легковесное синхронное подключение к SQLite для подсчета строк."""
    stats = {"tasks": 0, "ticks": 0, "personality_traits": 0, "mental_states": 0, "drives": 0}

    if not SQL_DB_FILE.exists():
        return stats

    try:
        conn = sqlite3.connect(SQL_DB_FILE)
        cursor = conn.cursor()
        for table in stats.keys():
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                # Таблицы еще нет
                pass
        conn.close()
    except Exception:
        pass

    return stats


def _get_vector_stats() -> dict[str, int]:
    """
    Считаем записи напрямую через клиент.
    Так как агент выключен, блокировки базы нет, это абсолютно безопасно и быстро.
    """
    stats = {"knowledge": 0, "thoughts": 0}

    if not VECTOR_DB_DIR.exists():
        return stats

    try:
        # Легкое синхронное чтение
        client = QdrantClient(path=str(VECTOR_DB_DIR))
        for collection in stats.keys():
            try:
                stats[collection] = client.count(collection).count
            except Exception:
                pass
        client.close()
    except Exception:
        pass

    return stats


def _reset_sql() -> None:
    """Удаляет файл SQLite БД."""
    if SQL_DB_FILE.exists():
        SQL_DB_FILE.unlink()
        print_success("База данных SQL (Долгосрочная память) успешно очищена.")
    else:
        print_info("База SQL уже пуста.")


def _reset_vector() -> None:
    """Удаляет папку Qdrant БД."""
    if VECTOR_DB_DIR.exists():
        shutil.rmtree(VECTOR_DB_DIR)
        print_success("Векторная БД (Семантическая память) успешно очищена.")
    else:
        print_info("Векторная БД уже пуста.")


def memory_reset_screen() -> None:
    """Главный цикл экрана сброса памяти."""
    if _is_agent_running():
        print_error("Ошибка: Нельзя сбрасывать память во время работы агента.")
        print_info("Остановите агента в главном меню перед очисткой БД.")
        wait_for_enter()
        return

    style = get_custom_style()

    while True:
        draw_header()

        sql_stats = _get_sql_stats()
        vec_stats = _get_vector_stats()

        # Формируем список. Separator не реагирует на стрелочки.
        choices = [
            questionary.Separator("Vector DB (Семантическая память)"),
            questionary.Separator(f"  Knowledge: {vec_stats['knowledge']} записей"),
            questionary.Separator(f"  Thoughts:  {vec_stats['thoughts']} записей"),
            questionary.Choice("🔥 Сжечь Vector DB", "clean_vector"),
            questionary.Separator(" "),  # Пустая строка для воздуха
            questionary.Separator("SQL DB"),
            questionary.Separator(f"  Mental States: {sql_stats['mental_states']} записей"),
            questionary.Separator(f"  Tasks:         {sql_stats['tasks']} записей"),
            questionary.Separator(
                f"  Traits:        {sql_stats['personality_traits']} записей"
            ),
            questionary.Separator(f"  Drives:        {sql_stats['drives']} записей"),
            questionary.Separator(f"  Ticks:         {sql_stats['ticks']} записей"),
            questionary.Choice("🔥 Сжечь SQL DB", "clean_sql"),
            questionary.Separator(" "),  # Пустая строка для воздуха
            questionary.Choice("❌ Выход в главное меню", "exit"),
        ]

        choice = questionary.select(
            "Для выбора того, что очистить - выберите нужный пункт и нажмите Enter:",
            choices=choices,
            style=style,
            qmark=" ",  # <-- Надежно прячем знак вопроса пробелом
            instruction="\n  (Стрелочки ↑/↓ для навигации)",
        ).ask()

        if choice is None or choice == "exit":
            break

        # Защита от дурака
        confirm = questionary.confirm(
            "⚠️ Вы уверены? Это действие необратимо удалит всю накопленную память.",
            default=False,
            qmark=" ",  # Здесь тоже убираем вопрос
        ).ask()

        if confirm:
            print()  # Пустая строка для красоты
            if choice == "clean_vector":
                _reset_vector()
            elif choice == "clean_sql":
                _reset_sql()

            wait_for_enter()

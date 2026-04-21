"""
Экран для сброса памяти агента (БД).
Позволяет физически удалить локальные файлы БД (SQLite и Vector).
Безопасно работает только при выключенном агенте.
"""

import shutil
import sqlite3
from pathlib import Path
import questionary

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
    """
    Легковесное синхронное подключение к SQLite для подсчета строк.
    """

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
    Считаем папки внутри Qdrant (KISS-подход без поднятия тяжелого клиента).
    """

    stats = {"knowledge": 0, "thoughts": 0}

    if not VECTOR_DB_DIR.exists():
        return stats

    for collection in stats.keys():
        points_dir = VECTOR_DB_DIR / "collection" / collection / "points"
        if points_dir.exists():
            # Qdrant хранит каждый вектор как файл(ы) внутри points.
            # Если папка существует, считаем, что записи есть.
            # Для точного подсчета нужен запуск клиента, но мы используем грубую оценку
            # (файлы *.point).
            count = len(list(points_dir.rglob("*.point")))
            stats[collection] = count

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

        # Формируем красиво отформатированный список
        choices = [
            questionary.Separator("--- Vector DB (Семантическая память) ---"),
            questionary.Choice(f"Knowledge: {vec_stats['knowledge']} записей", "none"),
            questionary.Choice(f"Thoughts:  {vec_stats['thoughts']} записей", "none"),
            questionary.Choice("🔥 Сжечь Vector DB", "clean_vector"),
            questionary.Separator("--- SQL DB (Долгосрочная память) ---"),
            questionary.Choice(f"Mental States: {sql_stats['mental_states']} записей", "none"),
            questionary.Choice(f"Tasks:         {sql_stats['tasks']} записей", "none"),
            questionary.Choice(
                f"Traits:        {sql_stats['personality_traits']} записей", "none"
            ),
            questionary.Choice(f"Drives:        {sql_stats['drives']} записей", "none"),
            questionary.Choice(f"Ticks (Logs):  {sql_stats['ticks']} записей", "none"),
            questionary.Choice("🔥 Сжечь SQL DB", "clean_sql"),
            questionary.Separator(),
            questionary.Choice("❌ Выход в главное меню", "exit"),
        ]

        choice = questionary.select(
            "Для выбора того, что очистить - выберите нужный пункт и нажмите Enter:",
            choices=choices,
            style=style,
            instruction="(Стрелочки ↑/↓ для навигации)",
        ).ask()

        if choice is None or choice == "exit":
            break

        if choice == "none":
            # Юзер кликнул по информационному полю (например, "Tasks: 5 записей")
            continue

        # Защита от дурака
        confirm = questionary.confirm(
            "⚠️ Вы уверены? Это действие необратимо удалит всю накопленную память.",
            default=False,
        ).ask()

        if confirm:
            print()  # Пустая строка для красоты
            if choice == "clean_vector":
                _reset_vector()
            elif choice == "clean_sql":
                _reset_sql()

            wait_for_enter()

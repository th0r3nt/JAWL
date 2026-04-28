import sqlite3
import shutil
import uuid
import textwrap
from datetime import datetime, timezone
from pathlib import Path
import questionary
from ruamel.yaml import YAML
from qdrant_client import QdrantClient, models

from src.cli.widgets.ui import (
    draw_header,
    get_custom_style,
    print_error,
    print_info,
    print_success,
    wait_for_enter,
    clear_screen,
)
from src.cli.screens.agent_control import _is_agent_running

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

DB_DIR = ROOT_DIR / "src" / "utils" / "local" / "data"
SQL_DB_FILE = DB_DIR / "sql" / "db" / "agent.db"
VECTOR_DB_DIR = DB_DIR / "vector" / "db"

SETTINGS_FILE = ROOT_DIR / "config" / "settings.yaml"
SETTINGS_EXAMPLE = ROOT_DIR / "config" / "settings.example.yaml"

yaml = YAML()
yaml.preserve_quotes = True

# ==================================================================
# УТИЛИТЫ
# ==================================================================


def _get_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return yaml.load(f)
    except UnicodeDecodeError:
        with open(SETTINGS_FILE, "r", encoding="cp1251") as f:
            return yaml.load(f)


def _save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        yaml.dump(settings, f)


def _ensure_settings_exists() -> bool:
    """Проверяет наличие файла settings.yaml, если нет - копирует example."""

    if not SETTINGS_FILE.exists():
        if SETTINGS_EXAMPLE.exists():
            shutil.copy(SETTINGS_EXAMPLE, SETTINGS_FILE)
            print_info(" Создан базовый файл конфигурации settings.yaml из .example")
        else:
            print_error("Не найден базовый файл конфигурации (settings.example.yaml).")
            return False
    return True


def _run_sql(query: str, params: tuple = (), fetchall: bool = False, fetchone: bool = False):
    """Выполняет сырой SQL запрос. Безопасно открывает и закрывает соединение."""
    if not SQL_DB_FILE.exists():
        return None
    conn = sqlite3.connect(SQL_DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if fetchall:
            res = cursor.fetchall()
        elif fetchone:
            res = cursor.fetchone()
        else:
            conn.commit()
            res = True
    except sqlite3.OperationalError:
        res = None
    finally:
        conn.close()
    return res


def _get_sql_stats() -> dict:
    stats = {
        "tasks": 0,
        "personality_traits": 0,
        "mental_states": 0,
        "drives_fund": 0,
        "drives_cust": 0,
    }
    if not SQL_DB_FILE.exists():
        return stats
    for table in ["tasks", "personality_traits", "mental_states"]:
        res = _run_sql(f"SELECT COUNT(*) FROM {table}", fetchone=True)
        if res:
            stats[table] = res[0]
    res = _run_sql("SELECT type, COUNT(*) FROM drives GROUP BY type", fetchall=True)
    if res:
        for row in res:
            if row[0] == "fundamental":
                stats["drives_fund"] = row[1]
            elif row[0] == "custom":
                stats["drives_cust"] = row[1]
    return stats


def _get_vector_stats() -> dict:
    stats = {"knowledge": 0, "thoughts": 0}
    if not VECTOR_DB_DIR.exists():
        return stats
    try:
        client = QdrantClient(path=str(VECTOR_DB_DIR))
        for coll in stats.keys():
            try:
                stats[coll] = client.count(coll).count
            except Exception:
                pass
        client.close()
    except Exception:
        pass
    return stats


# ==================================================================
# CRUD МЕНЮ ДЛЯ SQL МОДУЛЕЙ
# ==================================================================


def _manage_sql_module(
    module_name: str, table_name: str, config_key: str, limit_key: str, display_fields: list
):
    """Универсальный экран управления (Tasks, Traits, Mental States)."""
    style = get_custom_style()
    settings = _get_settings()
    cfg = settings["system"]["sql"][config_key]

    while True:
        clear_screen()
        status_str = "[ON]" if cfg["enabled"] else "[OFF]"
        stats = _get_sql_stats()
        current_count = stats.get(table_name, 0)

        print_info(f" Управление модулем {module_name} {status_str}")
        print(f"  Записей: {current_count} / {cfg[limit_key]}\n")

        choice = questionary.select(
            "Выберите действие:",
            choices=[
                questionary.Choice(f"Включить / Выключить (сейчас {status_str})", "toggle"),
                questionary.Choice("Изменить максимальный лимит", "change_limit"),
                questionary.Choice("➕ Добавить новую запись", "add_record"),
                questionary.Choice(f"❌ Удалить записи из {module_name}", "delete_records"),
                questionary.Separator(" "),
                questionary.Choice("↩ Назад", "back"),
            ],
            style=style,
            qmark="",
            instruction="",
        ).ask()

        if choice == "back" or choice is None:
            break

        elif choice == "toggle":
            cfg["enabled"] = not cfg["enabled"]
            _save_settings(settings)
            print_success(
                f"Модуль {module_name} {'включен' if cfg['enabled'] else 'выключен'}."
            )
            wait_for_enter()

        elif choice == "change_limit":
            new_limit = questionary.text(
                f"Новый лимит (сейчас {cfg[limit_key]}):", default=str(cfg[limit_key])
            ).ask()
            if new_limit and new_limit.isdigit():
                cfg[limit_key] = int(new_limit)
                _save_settings(settings)
                print_success("Лимит обновлен.")
            else:
                print_error("Введено не число.")
            wait_for_enter()

        elif choice == "add_record":
            if not SQL_DB_FILE.exists():
                print_error("БД еще не создана. Сначала запустите агента.")
                wait_for_enter()
                continue

            if current_count >= cfg[limit_key]:
                print_error(
                    "Достигнут максимальный лимит записей. Удалите старые или увеличьте лимит."
                )
                wait_for_enter()
                continue

            record_id = str(uuid.uuid4())[:8]

            if table_name == "tasks":
                title = questionary.text("Короткое название задачи:").ask()
                if not title:
                    continue
                desc = questionary.text("Полное описание:").ask()
                if not desc:
                    continue

                # JSON-пустышки
                empty_list_json = "[]"

                _run_sql(
                    """INSERT INTO tasks 
                    (id, title, description, status, progress, tags, dependencies, subtasks, due_date, context) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record_id,
                        title,
                        desc,
                        "todo",
                        0,
                        empty_list_json,
                        empty_list_json,
                        empty_list_json,
                        None,
                        None,
                    ),
                )
                print_success("Задача успешно добавлена.")

            elif table_name == "personality_traits":
                name = questionary.text("Название черты (обязательно):").ask()
                if not name:
                    continue
                desc = questionary.text("Описание (обязательно):").ask()
                if not desc:
                    continue

                _run_sql(
                    "INSERT INTO personality_traits (id, name, description, reason, context) VALUES (?, ?, ?, ?, ?)",
                    (record_id, name, desc, "Добавлено вручную пользователем", None),
                )
                print_success("Черта личности успешно добавлена.")

            elif table_name == "mental_states":
                name = questionary.text("Имя/Название сущности (обязательно):").ask()
                if not name:
                    continue

                tier = questionary.select(
                    "Уровень важности (tier):",
                    choices=["high", "medium", "low", "background"],
                    style=style,
                    qmark="",
                ).ask()
                category = questionary.select(
                    "Категория (category):",
                    choices=["subject", "object"],
                    style=style,
                    qmark="",
                ).ask()

                desc = questionary.text("Описание (кто/что это):").ask()
                status = questionary.text(
                    "Текущий статус (напр. 'В ожидании', 'Online'):"
                ).ask()

                if name and desc and status:
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
                    _run_sql(
                        "INSERT INTO mental_states (id, name, tier, category, updated_at, description, status, context, related_information) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (record_id, name, tier, category, now_str, desc, status, None, None),
                    )
                    print_success("Сущность успешно добавлена в память.")

            wait_for_enter()

        elif choice == "delete_records":
            if not SQL_DB_FILE.exists():
                print_error("База данных еще не создана. Сначала запустите агента.")
                wait_for_enter()
                continue

            fields_str = ", ".join(display_fields)
            records = _run_sql(f"SELECT id, {fields_str} FROM {table_name}", fetchall=True)

            if not records:
                print_info("Список пуст.")
                wait_for_enter()
                continue

            del_choices = [
                questionary.Choice(f"[{r[0]}] {r[1]} - {r[2]}", r[0]) for r in records
            ]
            del_choices.append(questionary.Separator(" "))
            del_choices.append(questionary.Choice("↩ Отмена", "cancel"))

            del_id = questionary.select(
                "Выберите запись для удаления:\n", choices=del_choices, style=style, qmark=""
            ).ask()

            if del_id and del_id != "cancel":
                if questionary.confirm(
                    f"Удалить запись {del_id}?", default=False, qmark=""
                ).ask():
                    _run_sql(f"DELETE FROM {table_name} WHERE id=?", (del_id,))
                    print_success("Запись удалена.")
                wait_for_enter()


def _manage_drives_screen():
    """Специфичный экран для мотиваций (Drives), т.к. там можно добавлять кастомные."""
    style = get_custom_style()

    while True:
        clear_screen()
        settings = _get_settings()
        cfg = settings["system"]["sql"]["drives"]
        stats = _get_sql_stats()
        status_str = "[ON]" if cfg["enabled"] else "[OFF]"

        print_info(f" Управление модулем Drives {status_str}")
        print(f"  Базовых мотиваций: {stats['drives_fund']}")
        print(f"  Кастомных мотиваций: {stats['drives_cust']} / {cfg['max_custom_drives']}\n")

        choice = questionary.select(
            "Выберите действие:",
            choices=[
                questionary.Choice(f"Включить / Выключить (сейчас {status_str})", "toggle"),
                questionary.Choice("Изменить лимит кастомных мотиваций", "change_limit"),
                questionary.Choice("➕ Добавить новую кастомную мотивацию", "add_drive"),
                questionary.Choice("❌ Удалить кастомную мотивацию", "del_drive"),
                questionary.Separator(" "),
                questionary.Choice("↩ Назад", "back"),
            ],
            style=style,
            qmark="",
            instruction="",
        ).ask()

        if choice == "back" or choice is None:
            break

        elif choice == "toggle":
            cfg["enabled"] = not cfg["enabled"]
            _save_settings(settings)
            print_success(f"Модуль Drives {'включен' if cfg['enabled'] else 'выключен'}.")
            wait_for_enter()

        elif choice == "change_limit":
            new_limit = questionary.text(
                "Новый лимит:", default=str(cfg["max_custom_drives"])
            ).ask()
            if new_limit and new_limit.isdigit():
                cfg["max_custom_drives"] = int(new_limit)
                _save_settings(settings)
                print_success("Лимит обновлен.")
            wait_for_enter()

        elif choice == "add_drive":
            if not SQL_DB_FILE.exists():
                print_error(
                    "БД еще не создана. Запустите агента хотя бы один раз, чтобы создать таблицы."
                )
                wait_for_enter()
                continue

            if stats["drives_cust"] >= cfg["max_custom_drives"]:
                print_error("Достигнут лимит кастомных мотиваций.")
                wait_for_enter()
                continue

            name = questionary.text("Название мотивации (напр. 'Любовь к яблокам'):").ask()
            desc = questionary.text("Описание (почему агент должен это делать):").ask()
            decay = questionary.text("Скорость дефицита (от 0.1 до 100):", default="5.0").ask()

            if name and desc and decay:
                try:
                    decay_float = float(decay)
                    d_id = str(uuid.uuid4())[:8]
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000000")
                    _run_sql(
                        "INSERT INTO drives (id, name, type, description, decay_rate, last_satisfied_at, recent_reflections) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (d_id, name, "custom", desc, decay_float, now_str, "[]"),
                    )
                    print_success(f"Мотивация '{name}' успешно добавлена.")
                except Exception as e:
                    print_error(f"Ошибка: {e}")
            wait_for_enter()

        elif choice == "del_drive":
            if not SQL_DB_FILE.exists():
                continue
            records = _run_sql(
                "SELECT id, name, decay_rate FROM drives WHERE type='custom'", fetchall=True
            )
            if not records:
                print_info("Кастомных мотиваций нет.")
                wait_for_enter()
                continue

            del_choices = [
                questionary.Choice(f"[{r[0]}] {r[1]} (Рост: {r[2]}%)", r[0]) for r in records
            ]
            del_choices.append(questionary.Separator(" "))
            del_choices.append(questionary.Choice("↩ Отмена", "cancel"))

            del_id = questionary.select(
                "Выберите мотивацию для удаления:", choices=del_choices, style=style, qmark=""
            ).ask()
            if del_id and del_id != "cancel":
                if questionary.confirm("Точно удалить?", default=False, qmark="").ask():
                    _run_sql("DELETE FROM drives WHERE id=? AND type='custom'", (del_id,))
                    print_success("Удалено.")
                wait_for_enter()


# ==================================================================
# CRUD МЕНЮ ДЛЯ VECTOR DB
# ==================================================================


def _manage_vector_collection(collection_name: str):
    """Экран управления знаниями или мыслями с пагинацией и переносом длинных строк."""
    style = get_custom_style()

    limit_per_page = 10
    current_page_idx = 0
    offset_history = [None]
    records_cache = []
    next_offset = None

    while True:
        clear_screen()
        if not VECTOR_DB_DIR.exists():
            print_error("Векторная БД не существует.")
            wait_for_enter()
            break

        try:
            client = QdrantClient(path=str(VECTOR_DB_DIR))
            total = client.count(collection_name).count

            if not records_cache and total > 0:
                current_req_offset = offset_history[current_page_idx]
                records_cache, next_offset = client.scroll(
                    collection_name=collection_name,
                    limit=limit_per_page,
                    offset=current_req_offset,
                    with_payload=True,
                )

                if next_offset is not None and current_page_idx + 1 == len(offset_history):
                    offset_history.append(next_offset)
            client.close()
        except Exception as e:
            print_error(f"Ошибка чтения БД: {e}")
            wait_for_enter()
            break

        # Формируем заголовок меню (он всегда будет виден над списком)
        if total > 0 and records_cache:
            start_idx = current_page_idx * limit_per_page + 1
            end_idx = start_idx + len(records_cache) - 1
            menu_title = (
                f"Коллекция '{collection_name}' | Страница {current_page_idx + 1} | Записи {start_idx}-{end_idx} из {total}\n"
                f" Выберите запись для удаления:\n"
            )
        else:
            menu_title = f"Коллекция '{collection_name}' пуста.\n Выберите действие:"

        choices = []
        for r in records_cache:
            text = r.payload.get("text", "").replace("\n", " ")
            short_text = text[:400] + "..." if len(text) > 400 else text

            wrapped_lines = textwrap.wrap(
                short_text, width=80
            )  # Чуть пошире, чтобы меньше строк было

            if not wrapped_lines:
                label = f"[{r.id[:8]}] [Пустая запись]"
            else:
                label = f"[{r.id[:8]}] {wrapped_lines[0]}"
                indent = " " * 11
                for line in wrapped_lines[1:]:
                    label += f"\n{indent}{line}"

            choices.append(questionary.Choice(label, r.id))
            # Воздух между записями
            choices.append(questionary.Separator(" "))

        # Навигация и управление
        if current_page_idx > 0:
            choices.append(questionary.Choice("⬅️ Предыдущая страница", "prev_page"))

        if next_offset is not None:
            choices.append(questionary.Choice("➡️ Следующая страница", "next_page"))

        if len(choices) > 0 and isinstance(choices[-1], questionary.Choice):
            choices.append(questionary.Separator(" "))

        choices.append(questionary.Choice("🧨 Очистить всю коллекцию", "nuke"))
        choices.append(questionary.Choice("↩ Назад", "back"))

        choice = questionary.select(
            menu_title, choices=choices, style=style, qmark="ℹ ", instruction=""
        ).ask()

        if choice == "back" or choice is None:
            break

        elif choice == "next_page":
            current_page_idx += 1
            records_cache = []
            continue

        elif choice == "prev_page":
            current_page_idx -= 1
            records_cache = []
            continue

        elif choice == "nuke":
            if questionary.confirm(
                f"ВНИМАНИЕ! Это удалит ВСЕ записи из {collection_name}. Уверены?",
                default=False,
                qmark="⚠️ ",
            ).ask():
                client = QdrantClient(path=str(VECTOR_DB_DIR))
                size = _get_settings()["system"]["vector_db"]["vector_size"]
                client.delete_collection(collection_name)
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=size, distance=models.Distance.COSINE
                    ),
                )
                client.close()
                records_cache = []
                current_page_idx = 0
                offset_history = [None]
                next_offset = None

                print_success(f"Коллекция {collection_name} очищена.")
                wait_for_enter()

        else:
            if questionary.confirm("Удалить эту запись?", default=False, qmark="\n❓ ").ask():
                client = QdrantClient(path=str(VECTOR_DB_DIR))
                client.delete(
                    collection_name=collection_name,
                    points_selector=models.PointIdsList(points=[choice]),
                )
                client.close()

                records_cache = [r for r in records_cache if str(r.id) != choice]

                if not records_cache and current_page_idx > 0:
                    current_page_idx -= 1
                    offset_history = offset_history[: current_page_idx + 1]
                    next_offset = None

                print_success("Запись удалена.")
                wait_for_enter()


# ==================================================================
# ГЛАВНЫЙ ЭКРАН
# ==================================================================


def database_manager_screen() -> None:
    if _is_agent_running():
        print_error("Ошибка: Нельзя управлять базами данных во время работы агента.")
        print_info("Остановите агента в главном меню (чтобы избежать SQLite Locks).")
        wait_for_enter()
        return

    if not _ensure_settings_exists():
        wait_for_enter()
        return

    style = get_custom_style()

    while True:
        draw_header()

        settings = _get_settings()
        sql_cfg = settings.get("system", {}).get("sql", {})

        s_stats = _get_sql_stats()
        v_stats = _get_vector_stats()

        ms_on = "[ON] " if sql_cfg.get("mental_states", {}).get("enabled") else "[OFF]"
        ts_on = "[ON] " if sql_cfg.get("tasks", {}).get("enabled") else "[OFF]"
        tr_on = "[ON] " if sql_cfg.get("personality_traits", {}).get("enabled") else "[OFF]"
        dr_on = "[ON] " if sql_cfg.get("drives", {}).get("enabled") else "[OFF]"

        choices = [
            questionary.Separator("🗂️ SQL DB"),
            questionary.Choice(
                f" ● Mental States {ms_on}  (Сущности: {s_stats['mental_states']}/{sql_cfg['mental_states']['max_entities']})",
                "ms",
            ),
            questionary.Choice(
                f" ● Tasks         {ts_on}  (Задачи: {s_stats['tasks']}/{sql_cfg['tasks']['max_tasks']})",
                "tasks",
            ),
            questionary.Choice(
                f" ● Traits        {tr_on}  (Черты: {s_stats['personality_traits']}/{sql_cfg['personality_traits']['max_traits']})",
                "traits",
            ),
            questionary.Choice(
                f" ● Drives        {dr_on}  (Мотиваций: {s_stats['drives_fund']} баз., {s_stats['drives_cust']}/{sql_cfg['drives']['max_custom_drives']} каст.)",
                "drives",
            ),
            questionary.Choice("Стереть реляционную базу данных", "clean_sql"),
            questionary.Separator(" "),
            questionary.Separator(" "),
            questionary.Separator("🗂️ Vector DB"),
            questionary.Choice(
                f" ● Knowledge            ({v_stats['knowledge']} записей)", "knowledge"
            ),
            questionary.Choice(
                f" ● Thoughts             ({v_stats['thoughts']} записей)", "thoughts"
            ),
            questionary.Choice("Стереть векторную базу данных", "clean_vector"),
            questionary.Separator(" "),
            questionary.Separator(" "),
            questionary.Choice("❌ Выход в главное меню", "exit"),
        ]

        choice = questionary.select(
            "Выберите модуль для управления:",
            choices=choices,
            style=style,
            qmark="",
            instruction="\n (Стрелочки ↑/↓ для навигации)\n",
        ).ask()

        if choice is None or choice == "exit":
            break

        # SQL
        if choice == "drives":
            _manage_drives_screen()

        elif choice == "ms":
            _manage_sql_module(
                "Mental States",
                "mental_states",
                "mental_states",
                "max_entities",
                ["name", "status"],
            )

        elif choice == "tasks":
            _manage_sql_module(
                "Tasks", "tasks", "tasks", "max_tasks", ["title", "status", "progress"]
            )

        elif choice == "traits":
            _manage_sql_module(
                "Traits",
                "personality_traits",
                "personality_traits",
                "max_traits",
                ["name", "description"],
            )

        # Vector
        elif choice == "knowledge":
            _manage_vector_collection("knowledge")

        elif choice == "thoughts":
            _manage_vector_collection("thoughts")

        # Global Delete
        elif choice == "clean_sql":
            if questionary.confirm(
                "⚠️ Вы уверены? Это необратимо удалит SQL базу.", default=False, qmark=""
            ).ask():
                if SQL_DB_FILE.exists():
                    SQL_DB_FILE.unlink()
                    print_success("База SQL очищена.")
                else:
                    print_info("База SQL уже пуста.")
                wait_for_enter()

        elif choice == "clean_vector":
            if questionary.confirm(
                "⚠️ Вы уверены? Это необратимо удалит Vector базу.", default=False, qmark=""
            ).ask():
                if VECTOR_DB_DIR.exists():
                    shutil.rmtree(VECTOR_DB_DIR)
                    print_success("Векторная база очищена.")
                else:
                    print_info("Векторная база уже пуста.")
                wait_for_enter()

"""
Database Manager CLI Screen.

Provides an interactive control panel for local database inspection and CRUD.
Enables management of SQL (Tasks, Traits, Mental States, Drives) and
Vector DB (Knowledge, Thoughts) collections.
"""

import sqlite3
import shutil
import uuid
import textwrap
from datetime import datetime, timezone
from pathlib import Path
import questionary
from ruamel.yaml import YAML
from qdrant_client import QdrantClient, models
import kuzu

from src.cli.widgets.ui import (
    draw_header,
    get_custom_style,
    print_error,
    print_info,
    print_success,
    wait_for_enter,
    clear_screen,
    set_window_title,
)
from src.cli.screens.agent_control import _is_agent_running

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
LOCAL_DATA_DIR = ROOT_DIR / "src" / "utils" / "local" / "data"

SQL_DB_FILE = LOCAL_DATA_DIR / "sql" / "db" / "agent.db"
VECTOR_DB_DIR = LOCAL_DATA_DIR / "vector" / "db"
GRAPH_DB_DIR = LOCAL_DATA_DIR / "graph"

INTERFACES_DIR = LOCAL_DATA_DIR / "interfaces"

SETTINGS_FILE = ROOT_DIR / "config" / "settings.yaml"
SETTINGS_EXAMPLE = ROOT_DIR / "config" / "settings.example.yaml"

yaml = YAML()
yaml.preserve_quotes = True


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
    """Creates base settings.yaml from template if missing."""

    if not SETTINGS_FILE.exists():
        if SETTINGS_EXAMPLE.exists():
            shutil.copy(SETTINGS_EXAMPLE, SETTINGS_FILE)
            print_info(" Created base configuration file settings.yaml from .example")
        else:
            print_error("Base configuration template not found (settings.example.yaml).")
            return False
    return True


def _run_sql(query: str, params: tuple = (), fetchall: bool = False, fetchone: bool = False):
    """Executes raw SQLite query."""
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


def _get_graph_stats() -> dict:
    stats = {"concepts": 0}
    db_path = GRAPH_DB_DIR / "agent_graph.db"
    if not db_path.exists():
        return stats
    try:
        db = kuzu.Database(str(db_path))
        conn = kuzu.Connection(db)
        res = conn.execute("MATCH (n:Concept) RETURN count(n)")
        if res.has_next():
            stats["concepts"] = res.get_next()[0]
    except Exception:
        pass
    return stats


# ==================================================================
# CRUD SCREEN FOR SQL MODULES
# ==================================================================


def _manage_sql_module(
    module_name: str, table_name: str, config_key: str, limit_key: str, display_fields: list
):
    """Universal CRUD screen for SQL tables."""
    style = get_custom_style()
    settings = _get_settings()
    cfg = settings["system"]["db"]["sql"][config_key]

    while True:
        clear_screen()
        status_str = "[ON]" if cfg["enabled"] else "[OFF]"
        stats = _get_sql_stats()
        current_count = stats.get(table_name, 0)

        print_info(f" Managing module {module_name} {status_str}")
        print(f"  Records: {current_count} / {cfg[limit_key]}\n")

        choice = questionary.select(
            "Select action:",
            choices=[
                questionary.Separator(" "),
                questionary.Choice(f"Toggle On/Off (currently {status_str})", "toggle"),
                questionary.Choice("Change maximum limit", "change_limit"),
                questionary.Separator(" "),
                questionary.Choice("[+] Add new record", "add_record"),
                questionary.Choice(f"[x] Delete records from {module_name}", "delete_records"),
                questionary.Separator(" "),
                questionary.Choice("↩ Back", "back"),
            ],
            style=style,
            qmark="",
            instruction=" ",
        ).ask()

        if choice == "back" or choice is None:
            break

        elif choice == "toggle":
            cfg["enabled"] = not cfg["enabled"]
            _save_settings(settings)
            print_success(
                f"Module {module_name} {'enabled' if cfg['enabled'] else 'disabled'}."
            )
            wait_for_enter()

        elif choice == "change_limit":
            new_limit = questionary.text(
                f"New limit (currently {cfg[limit_key]}):", default=str(cfg[limit_key])
            ).ask()
            if new_limit and new_limit.isdigit():
                cfg[limit_key] = int(new_limit)
                _save_settings(settings)
                print_success("Limit updated.")
            else:
                print_error("Input is not a number.")
            wait_for_enter()

        elif choice == "add_record":
            if not SQL_DB_FILE.exists():
                print_error("DB not created yet. Start the agent first.")
                wait_for_enter()
                continue

            if current_count >= cfg[limit_key]:
                print_error(
                    "Maximum records limit reached. Delete old records or increase limit."
                )
                wait_for_enter()
                continue

            record_id = str(uuid.uuid4())[:8]

            if table_name == "tasks":
                title = questionary.text("Short task title:").ask()
                if not title:
                    continue
                desc = questionary.text("Full description:").ask()
                if not desc:
                    continue

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
                print_success("Task successfully added.")

            elif table_name == "personality_traits":
                name = questionary.text("Trait name (required):").ask()
                if not name:
                    continue
                desc = questionary.text("Description (required):").ask()
                if not desc:
                    continue

                _run_sql(
                    "INSERT INTO personality_traits (id, name, description, reason, context) VALUES (?, ?, ?, ?, ?)",
                    (record_id, name, desc, "Added manually by user", None),
                )
                print_success("Personality trait successfully added.")

            elif table_name == "mental_states":
                name = questionary.text("Entity name (required):").ask()
                if not name:
                    continue

                tier = questionary.select(
                    "Importance level (tier):",
                    choices=["high", "medium", "low", "background"],
                    style=style,
                    qmark="",
                ).ask()
                category = questionary.select(
                    "Category (category):",
                    choices=["subject", "object"],
                    style=style,
                    qmark="",
                ).ask()

                desc = questionary.text("Description (who/what is this):").ask()
                status = questionary.text("Current status (e.g., 'Pending', 'Online'):").ask()

                if name and desc and status:
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
                    _run_sql(
                        "INSERT INTO mental_states (id, name, tier, category, updated_at, description, status, context, related_information) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (record_id, name, tier, category, now_str, desc, status, None, None),
                    )
                    print_success("Entity successfully added to memory.")

            wait_for_enter()

        elif choice == "delete_records":
            if not SQL_DB_FILE.exists():
                print_error("DB not created yet. Start the agent first.")
                wait_for_enter()
                continue

            fields_str = ", ".join(display_fields)
            records = _run_sql(f"SELECT id, {fields_str} FROM {table_name}", fetchall=True)

            if not records:
                print_info("The list is empty.")
                wait_for_enter()
                continue

            del_choices = [
                questionary.Choice(f"[{r[0]}] {r[1]} - {r[2]}", r[0]) for r in records
            ]
            del_choices.append(questionary.Separator(" "))
            del_choices.append(questionary.Choice("↩ Cancel", "cancel"))

            del_id = questionary.select(
                "Select record to delete:\n", choices=del_choices, style=style, qmark=""
            ).ask()

            if del_id and del_id != "cancel":
                if questionary.confirm(
                    f"Delete record {del_id}?", default=False, qmark=""
                ).ask():
                    _run_sql(f"DELETE FROM {table_name} WHERE id=?", (del_id,))
                    print_success("Record deleted.")
                wait_for_enter()


def _manage_drives_screen():
    """Specific dashboard for system Drives."""
    style = get_custom_style()

    while True:
        clear_screen()
        settings = _get_settings()
        cfg = settings["system"]["db"]["sql"]["drives"]
        stats = _get_sql_stats()
        status_str = "[ON]" if cfg["enabled"] else "[OFF]"

        print_info(f" Managing Drives module {status_str}")
        print(f"  Fundamental drives: {stats['drives_fund']}")
        print(f"  Custom drives: {stats['drives_cust']} / {cfg['max_custom_drives']}\n")

        choice = questionary.select(
            "Select action:",
            choices=[
                questionary.Choice(f"Toggle On/Off (currently {status_str})", "toggle"),
                questionary.Choice("Change custom drives limit", "change_limit"),
                questionary.Choice("[+] Add new custom drive", "add_drive"),
                questionary.Choice("[x] Delete custom drive", "del_drive"),
                questionary.Separator(" "),
                questionary.Choice("↩ Back", "back"),
            ],
            style=style,
            qmark="",
            instruction=" ",
        ).ask()

        if choice == "back" or choice is None:
            break

        elif choice == "toggle":
            cfg["enabled"] = not cfg["enabled"]
            _save_settings(settings)
            print_success(f"Drives module {'enabled' if cfg['enabled'] else 'disabled'}.")
            wait_for_enter()

        elif choice == "change_limit":
            new_limit = questionary.text(
                "New limit:", default=str(cfg["max_custom_drives"])
            ).ask()
            if new_limit and new_limit.isdigit():
                cfg["max_custom_drives"] = int(new_limit)
                _save_settings(settings)
                print_success("Limit updated.")
            wait_for_enter()

        elif choice == "add_drive":
            if not SQL_DB_FILE.exists():
                print_error(
                    "DB not created yet. Start the agent at least once to generate tables."
                )
                wait_for_enter()
                continue

            if stats["drives_cust"] >= cfg["max_custom_drives"]:
                print_error("Custom drives limit reached.")
                wait_for_enter()
                continue

            name = questionary.text("Drive name (e.g., 'Apple Craving'):").ask()
            desc = questionary.text("Description (why the agent must fulfill this):").ask()
            decay = questionary.text(
                "Deficit growth rate (from 0.1 to 100):", default="10.0"
            ).ask()
            interval = questionary.text(
                "Growth interval in seconds (e.g., 900):", default="900"
            ).ask()

            if name and desc and decay and interval:
                try:
                    decay_float = float(decay)
                    interval_int = int(interval)
                    d_id = str(uuid.uuid4())[:8]
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000000")
                    _run_sql(
                        "INSERT INTO drives (id, name, type, description, decay_rate, decay_interval_sec, last_satisfied_at, recent_reflections) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (d_id, name, "custom", desc, decay_float, interval_int, now_str, "[]"),
                    )
                    print_success(f"Drive '{name}' successfully added.")
                except Exception as e:
                    print_error(f"Error: {e}")
            wait_for_enter()

        elif choice == "del_drive":
            if not SQL_DB_FILE.exists():
                continue
            records = _run_sql(
                "SELECT id, name, decay_rate FROM drives WHERE type='custom'", fetchall=True
            )
            if not records:
                print_info("No custom drives found.")
                wait_for_enter()
                continue

            del_choices = [
                questionary.Choice(f"[{r[0]}] {r[1]} (Growth: {r[2]}%)", r[0]) for r in records
            ]
            del_choices.append(questionary.Separator(" "))
            del_choices.append(questionary.Choice("↩ Cancel", "cancel"))

            del_id = questionary.select(
                "Select drive to delete:", choices=del_choices, style=style, qmark=""
            ).ask()
            if del_id and del_id != "cancel":
                if questionary.confirm(
                    "Are you sure you want to delete?", default=False, qmark=""
                ).ask():
                    _run_sql("DELETE FROM drives WHERE id=? AND type='custom'", (del_id,))
                    print_success("Deleted.")
                wait_for_enter()


# ==================================================================
# CRUD SCREEN FOR VECTOR DB
# ==================================================================


def _manage_vector_collection(collection_name: str):
    """Interactive vector points manager with pagination."""
    style = get_custom_style()

    limit_per_page = 10
    current_page_idx = 0
    offset_history = [None]
    records_cache = []
    next_offset = None

    while True:
        clear_screen()
        if not VECTOR_DB_DIR.exists():
            print_error("Vector DB does not exist.")
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
            print_error(f"Error reading DB: {e}")
            wait_for_enter()
            break

        if total > 0 and records_cache:
            start_idx = current_page_idx * limit_per_page + 1
            end_idx = start_idx + len(records_cache) - 1
            menu_title = (
                f"Collection '{collection_name}' | Page {current_page_idx + 1} | Records {start_idx}-{end_idx} of {total}\n"
                f" Select record to delete:\n"
            )
        else:
            menu_title = f"Collection '{collection_name}' is empty.\n Select action:"

        choices = []
        for r in records_cache:
            text = r.payload.get("text", "").replace("\n", " ")
            short_text = text[:400] + "..." if len(text) > 400 else text

            wrapped_lines = textwrap.wrap(short_text, width=80)

            if not wrapped_lines:
                label = f"[{r.id[:8]}] [Empty Record]"
            else:
                label = f"[{r.id[:8]}] {wrapped_lines[0]}"
                indent = " " * 11
                for line in wrapped_lines[1:]:
                    label += f"\n{indent}{line}"

            choices.append(questionary.Choice(label, r.id))
            choices.append(questionary.Separator(" "))

        if current_page_idx > 0:
            choices.append(questionary.Choice("⬅️ Previous Page", "prev_page"))

        if next_offset is not None:
            choices.append(questionary.Choice("➡️ Next Page", "next_page"))

        if len(choices) > 0 and isinstance(choices[-1], questionary.Choice):
            choices.append(questionary.Separator(" "))

        choices.append(questionary.Choice("🧨 Clear Entire Collection", "nuke"))
        choices.append(questionary.Choice("↩ Back", "back"))

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
                f"Warning. This will delete ALL records from {collection_name}. Are you sure?",
                default=False,
                qmark="⚠️ ",
            ).ask():
                client = QdrantClient(path=str(VECTOR_DB_DIR))
                size = _get_settings()["system"]["db"]["vector"]["vector_size"]
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

                print_success(f"Collection {collection_name} cleared.")
                wait_for_enter()

        else:
            if questionary.confirm("Delete this record?", default=False, qmark="\n❓ ").ask():
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

                print_success("Record deleted.")
                wait_for_enter()


# ==================================================================
# MAIN SCREEN
# ==================================================================


def database_manager_screen() -> None:
    """
    Main database management screen.
    """

    set_window_title("JAWL - Database Manager")

    if _is_agent_running():
        print_error("Error: Cannot manage databases while the agent is running.")
        print_info("Stop the agent from the main menu (to avoid SQLite Locks).")
        wait_for_enter()
        return

    if not _ensure_settings_exists():
        wait_for_enter()
        return

    style = get_custom_style()

    while True:
        draw_header()

        settings = _get_settings()
        sql_cfg = settings.get("system", {}).get("db", {}).get("sql", {})

        s_stats = _get_sql_stats()
        v_stats = _get_vector_stats()
        g_stats = _get_graph_stats()

        ms_on = "[ON] " if sql_cfg.get("mental_states", {}).get("enabled") else "[OFF]"
        ts_on = "[ON] " if sql_cfg.get("tasks", {}).get("enabled") else "[OFF]"
        tr_on = "[ON] " if sql_cfg.get("personality_traits", {}).get("enabled") else "[OFF]"
        dr_on = "[ON] " if sql_cfg.get("drives", {}).get("enabled") else "[OFF]"

        choices = [
            questionary.Separator("[#] SQL DB"),
            questionary.Choice(
                f" ● Mental States {ms_on}  (Entities: {s_stats['mental_states']}/{sql_cfg['mental_states']['max_entities']})",
                "ms",
            ),
            questionary.Choice(
                f" ● Tasks         {ts_on}  (Tasks: {s_stats['tasks']}/{sql_cfg['tasks']['max_tasks']})",
                "tasks",
            ),
            questionary.Choice(
                f" ● Traits        {tr_on}  (Traits: {s_stats['personality_traits']}/{sql_cfg['personality_traits']['max_traits']})",
                "traits",
            ),
            questionary.Choice(
                f" ● Drives        {dr_on}  (Drives: {s_stats['drives_fund']} fund., {s_stats['drives_cust']}/{sql_cfg['drives']['max_custom_drives']} cust.)",
                "drives",
            ),
            questionary.Choice(" ● Erase Database", "clean_sql"),
            questionary.Separator(" "),
            questionary.Separator(" "),
            questionary.Separator("[#] Vector DB"),
            questionary.Choice(
                f" ● Knowledge            ({v_stats['knowledge']} records)", "knowledge"
            ),
            questionary.Choice(
                f" ● Thoughts             ({v_stats['thoughts']} records)", "thoughts"
            ),
            questionary.Choice(" ● Erase Database", "clean_vector"),
            questionary.Separator(" "),
            questionary.Separator("[#] Graph DB"),
            questionary.Choice(
                f" ● Concepts             ({g_stats['concepts']} records)", "dummy_graph_info"
            ),
            questionary.Choice(" ● Erase Database", "clean_graph"),
            questionary.Separator(" "),
            questionary.Separator("[#] Interfaces Cache"),
            questionary.Choice(
                " ● Clear cache (src/utils/local/data/interfaces/)", "clean_interfaces"
            ),
            questionary.Separator(" "),
            questionary.Choice("[x] Exit to main menu", "exit"),
        ]

        choice = questionary.select(
            "Select module to manage:",
            choices=choices,
            style=style,
            qmark="",
            instruction="\n (Arrows ↑/↓ for navigation)\n",
        ).ask()

        if choice is None or choice == "exit":
            break

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

        elif choice == "knowledge":
            _manage_vector_collection("knowledge")

        elif choice == "thoughts":
            _manage_vector_collection("thoughts")

        elif choice == "clean_sql":
            if questionary.confirm(
                "⚠️ Are you sure? This will irreversibly delete SQL DB.",
                default=False,
                qmark="",
            ).ask():
                if SQL_DB_FILE.exists():
                    SQL_DB_FILE.unlink()
                    print_success("SQL Database cleared.")
                else:
                    print_info("SQL Database is already empty.")
                wait_for_enter()

        elif choice == "clean_vector":
            if questionary.confirm(
                "⚠️ Are you sure? This will irreversibly delete Vector DB.",
                default=False,
                qmark="",
            ).ask():
                if VECTOR_DB_DIR.exists():
                    shutil.rmtree(VECTOR_DB_DIR)
                    print_success("Vector Database cleared.")
                else:
                    print_info("Vector Database is already empty.")
                wait_for_enter()

        elif choice == "clean_graph":
            if questionary.confirm(
                "⚠️ Are you sure? This will irreversibly delete Graph DB.",
                default=False,
                qmark="",
            ).ask():
                if GRAPH_DB_DIR.exists():
                    shutil.rmtree(GRAPH_DB_DIR, ignore_errors=True)
                    print_success("Graph Database successfully cleared.")
                else:
                    print_info("Graph Database is already empty.")
                wait_for_enter()

        elif choice == "clean_interfaces":
            if questionary.confirm(
                "⚠️ Are you sure? This will wipe browser history, Telegram sessions, folder tracking configurations, and custom dashboards. The agent will forget everything from L2 interfaces.",
                default=False,
                qmark="",
            ).ask():
                if INTERFACES_DIR.exists():
                    shutil.rmtree(INTERFACES_DIR, ignore_errors=True)
                    print_success(
                        "All interfaces cache successfully deleted. Sessions will be recreated on the next startup."
                    )
                else:
                    print_info("Interfaces folder is already empty.")
                wait_for_enter()

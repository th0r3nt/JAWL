# -*- coding: utf-8 -*-
"""
Договорённости консоли с фреймворком.

Консоль намеренно не меняет фреймворк, а приспосабливается к нему. Значит, она
опирается на его внутренности: имена файлов состояния, колонки таблиц, строку
рукопожатия терминала, пути в конфигах, формулировки в журнале.

Всё это может измениться в чужом коде, и тогда консоль сломается **молча**:
счётчик покажет ноль, чат не подключится, кнопка «Остановить» перестанет
работать. Тесты ниже дублируют эти договорённости с обеих сторон, чтобы
расхождение падало здесь, а не всплывало в интерфейсе.

Тестам не важно, кто прав — важно, что стороны разъехались.
"""

import re

import pytest

from src.web import agent, chat, config_io as cio, database, drives, logs, schema

ROOT = cio.ROOT_DIR


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


# ------------------------------------------------- управление жизнью агента

def test_pid_and_lock_paths_match_the_framework():
    """
    По этим файлам консоль понимает, запущен ли агент, и снимает зависший.
    Разъедутся — кнопка «Запустить» будет поднимать второго агента поверх
    работающего.
    """
    from src.utils import _tools

    assert agent.PID_FILE == _tools.get_pid_file_path()
    assert agent.LOCK_FILE == _tools.get_lock_file_path()


def test_stop_file_matches_the_orchestrator():
    """
    Мягкая остановка — это файл-сигнал, который ждёт оркестратор. Имя задано в
    двух местах: у него и у нас.
    """
    text = source("src/system/orchestrator.py")

    assert '"agent.stop"' in text, "оркестратор больше не ждёт этот файл"
    assert agent.STOP_FILE.name == "agent.stop"
    assert agent.STOP_FILE.parent == agent.DATA_DIR


def test_agent_is_started_by_the_same_entry_point():
    assert agent.MAIN_SCRIPT == ROOT / "src" / "main.py"
    assert agent.MAIN_SCRIPT.exists(), "точка входа агента переехала"


# ---------------------------------------------------------------- журнал

def test_log_file_matches_the_logger():
    """Вкладка «Логи» и разбор такта читают тот же файл, что пишет фреймворк."""
    text = source("src/utils/logger.py")

    assert "main.log" in text, "имя файла журнала изменилось"
    assert logs.LOG_FILE.name == "main.log"


def test_log_line_format_matches_the_formatter():
    """
    Разбор такта держится на порядке полей в строке. Формат задан одной строкой
    в logger.py — если её переставят, `LINE_RE` перестанет совпадать молча.
    """
    from src.web import tick

    text = source("src/utils/logger.py")
    fmt = re.search(r'file_fmt = "([^"]+)"', text).group(1)

    assert fmt == "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s", \
        "формат строки журнала изменился: %s" % fmt

    sample = "2026-08-25 04:07:30.525 - JAWL.Agent - INFO - [ReAct] Step 1/8."
    assert tick.LINE_RE.match(sample), "разбор не берёт строку своего же формата"


def test_log_timestamps_are_local_time():
    """
    Обратный отсчёт сравнивает отметку из журнала с `datetime.now()` без зоны.
    Это верно, только пока форматтер печатает местное время — то есть пока
    никто не подменил `converter`.
    """
    text = source("src/utils/logger.py")

    assert "converter" not in text, \
        "у форматтера появился свой converter — отметки могут быть не в местном времени"


# ---------------------------------------------------------------- мотиваторы

def test_drive_columns_match_the_table():
    """Читаем колонки поимённо: переименуют — получим пустую вкладку."""
    text = source("src/l1_databases/sql/tables.py")
    block = text[text.index("class DriveTable"):]
    block = block[:block.index("\nclass ", 1) if "\nclass " in block[1:] else len(block)]

    for column in ("id", "name", "type", "description", "decay_rate",
                   "decay_interval_sec", "last_satisfied_at", "recent_reflections"):
        assert re.search(r"\b%s\b" % column, block), "колонка исчезла: %s" % column


def test_drive_database_path_matches_the_builder():
    """Путь к базе задан в builder.py; консоль ходит по нему же."""
    text = source("src/builder.py")

    assert '"sql" / "db"' in text or "'sql' / 'db'" in text, "путь к базе изменился"
    assert drives.DB_FILE == database.SQL_DB_FILE, "две части консоли смотрят в разные базы"


def test_fundamental_drive_names_match_the_bootstrap():
    """
    Английские имена из базы переводятся в русские по словарю. Появится новый
    фундаментальный мотиватор — он покажется без перевода, и это надо заметить.
    """
    text = source("src/l1_databases/sql/management/drives/crud.py")
    block = text[text.index("fundamental_defs"):]
    block = block[:block.index("\n    async def", 1) if "\n    async def" in block else len(block)]

    declared = set(re.findall(r'"(Curiosity|Social|Mastery)"', block))
    assert declared == set(drives.FUNDAMENTAL_TITLES), \
        "состав фундаментальных мотиваторов разошёлся: %s" % sorted(declared)


def test_deficit_formula_is_still_the_same_shape():
    """
    Формула дефицита продублирована в консоли и сверяется числами в
    test_unit_drives. Здесь ловим более грубое: саму её пропажу.
    """
    text = source("src/l1_databases/sql/management/drives/crud.py")

    assert "_calculate_deficit" in text, "формула дефицита исчезла из фреймворка"
    assert "dynamic_reduction" in text, "флаг нелинейного накопления исчез"


# ---------------------------------------------------------------- хранилища

def test_vector_collection_names_match_the_manager():
    """Счётчики читают коллекции поимённо."""
    text = source("src/l1_databases/vector/manager.py")

    for name in database.VECTOR_COLLECTIONS:
        assert '"%s"' % name in text, "коллекция исчезла из фреймворка: %s" % name


def test_vector_storage_layout_is_still_sqlite():
    """
    Счётчики Qdrant читаются в обход клиента, прямо из `storage.sqlite` внутри
    коллекции. Это внутренность локального режима: сменят формат — цифры молча
    станут пустыми.
    """
    if not database.VECTOR_DB_DIR.exists():
        pytest.skip("векторная база ещё не создана")

    collections = database.VECTOR_DB_DIR / "collection"
    if not collections.exists():
        pytest.skip("коллекций пока нет")

    found = list(collections.glob("*/storage.sqlite"))
    assert found, "внутри коллекций больше нет storage.sqlite — счётчики ослепнут"


def test_graph_tables_match_the_schema():
    from src.l1_databases.graph import schema as graph_schema

    assert database.GRAPH_NODE_TABLE == graph_schema.GRAPH_NODE_TABLE
    assert database.CODE_NODE_TABLE == graph_schema.CODE_NODE_TABLE


def test_storage_paths_match_the_builder():
    """Все три базы и кэш моделей заданы в builder.py — сверяем хвосты путей."""
    text = source("src/builder.py")

    for fragment in ('"vector" / "db"', '"vector" / "embeddings"'):
        assert fragment in text, "путь изменился: %s" % fragment


# ---------------------------------------------------------------- терминал

def test_chat_handshake_matches_the_terminal_server():
    """
    Без точной строки рукопожатия агент молча закрывает соединение — так он
    отшивает сканеры портов, и чат выглядел бы просто неработающим.
    """
    text = source("src/l2_interfaces/host/terminal/client.py")

    assert '"JAWL_HANDSHAKE"' in text, "рукопожатие изменилось"
    assert chat.HANDSHAKE == b"JAWL_HANDSHAKE\n"


def test_chat_files_match_the_terminal_server():
    text = source("src/l2_interfaces/host/terminal/client.py")

    assert '"terminal.port"' in text, "имя файла порта изменилось"
    assert '"history.json"' in text, "имя файла истории изменилось"
    assert chat.PORT_FILE.name == "terminal.port"
    assert chat.HISTORY_FILE.name == "history.json"
    assert chat.PORT_FILE.parent == chat.HISTORY_FILE.parent == chat.TERMINAL_DIR


def test_chat_payload_keys_match_the_terminal_server():
    """Отправляем `text`, читаем `text` и `time` — ключи заданы на той стороне."""
    text = source("src/l2_interfaces/host/terminal/client.py")

    assert 'parsed.get("text"' in text, "сервер больше не читает ключ text"
    assert '{"text": text, "time": time_str}' in text, "формат ответа изменился"


def test_terminal_message_still_wakes_the_agent():
    """
    Смысл чата в том, что сообщение будит агента немедленно. Понизят уровень
    события — реплики начнут ждать планового такта.
    """
    from src.utils.event.registry import EventLevel, Events

    assert Events.HOST_TERMINAL_MESSAGE.level == EventLevel.CRITICAL, \
        "сообщение оператора больше не будит агента немедленно"


def test_terminal_interface_is_the_one_we_talk_to(interfaces_yaml):
    """Канал оператора должен существовать в конфигурации интерфейсов."""
    interfaces = interfaces_yaml

    assert cio.get_path(interfaces, "host.terminal.enabled") is not None, \
        "интерфейс терминала исчез из конфигурации"


# ---------------------------------------------------------------- конфигурация

def test_every_settings_path_exists_in_the_example():
    """
    Свежая установка копирует `settings.example.yaml`. Если поле есть только в
    рабочем конфиге, у нового пользователя консоль покажет пустую ячейку.
    """
    example = cio.load_yaml(ROOT / "config" / "settings.example.yaml")
    missing = [p for p in schema.SETTINGS_FIELDS.values()
               if cio.get_path(example, p, "\0") == "\0"]

    assert not missing, "нет в settings.example.yaml: %s" % missing


def test_every_interfaces_path_exists_in_the_example():
    example = cio.load_yaml(ROOT / "config" / "interfaces.example.yaml")
    missing = [p for p in schema.INTERFACES_FIELDS.values()
               if cio.get_path(example, p, "\0") == "\0"]

    assert not missing, "нет в interfaces.example.yaml: %s" % missing


@pytest.mark.parametrize("path", [
    "identity.agent_name",
    "system.heartbeat_interval",
    "system.continuous_cycle",
    "llm.max_react_steps",
    "system.db.vector.embedding_model",
    "system.db.sql.drives.dynamic_reduction",
])
def test_paths_used_outside_the_schema_still_exist(path, settings_yaml):
    """
    Эти ключи читаются напрямую модулями консоли, а не через `schema.py`, и
    потому не покрыты проверкой привязок.
    """
    settings = settings_yaml

    assert cio.get_path(settings, path, "\0") != "\0", "ключ исчез: %s" % path


def test_llm_key_prefix_matches_the_loader():
    """
    Ключи LLM собираются перебором `SUB_LLM_API_KEY_N`. Префикс задан в main.py —
    поменяют его, и консоль будет писать ключи, которых никто не прочитает.
    """
    text = source("src/main.py")
    prefixes = set(schema.ENV_LISTS.values())

    for prefix in prefixes:
        assert prefix in text, "префикс ключей не встречается в main.py: %s" % prefix


# ---------------------------------------------------------------- целостность

def test_console_does_not_import_framework_internals_for_writing():
    """
    Консоль читает фреймворк, но не должна вызывать его на запись: у неё нет
    его контекста, а параллельная правка разошлась бы с состоянием агента.
    """
    for path in sorted((ROOT / "src" / "web").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for banned in ("from src.l3_agent", "from src.l2_interfaces",
                       "from src.l0_state"):
            assert banned not in text, "%s тянет %s" % (path.name, banned)


def test_console_lives_only_in_its_own_folders():
    """Обещание из PROMPT_FRONTEND.md: код консоли не расползается по проекту."""
    import subprocess

    result = subprocess.run(["git", "status", "--porcelain"],
                            cwd=str(ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("git недоступен")

    allowed = ("web/", "src/web/", "tests/web/", "backup/", "start.bat",
               "test.bat", ".gitignore", "PROMPT_FRONTEND.md", "console.html")
    stray = []
    for line in result.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if path and not path.startswith(allowed):
            stray.append(path)

    assert not stray, "изменения вне папок консоли: %s" % stray


# ---------------------------------------------------------------- сторожа

def _duplicate_branches(path):
    """Условия, повторённые в одной цепочке if/elif: вторая ветка недостижима."""
    import ast

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        tests, cur = [], node
        while True:
            tests.append(ast.dump(cur.test))
            if len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
                cur = cur.orelse[0]
            else:
                break
        if len(tests) != len(set(tests)):
            hits.append(node.lineno)
    return hits


def test_no_new_unreachable_branches():
    """
    Сторож от копипасты: одно и то же условие дважды в цепочке `if/elif` делает
    вторую ветку недостижимой, и Python об этом молчит.

    Один такой случай в проекте уже есть и описан в web/FRAMEWORK_NOTES.md
    (пункт меню очистки не трогает песочницу). Исправлять его не наше дело —
    но новые появляться не должны.
    """
    known = {"database_manager.py"}

    offenders = {}
    for path in sorted(ROOT.joinpath("src").rglob("*.py")):
        if "__pycache__" in str(path) or path.name in known:
            continue
        lines = _duplicate_branches(path)
        if lines:
            offenders[path.relative_to(ROOT).as_posix()] = lines

    assert not offenders, "недостижимые ветки: %s" % offenders


def test_the_known_unreachable_branch_is_still_there():
    """
    Обратная сторона: если дубль в CLI починят, запись в FRAMEWORK_NOTES.md
    устареет и начнёт вводить в заблуждение. Тест напомнит убрать её.
    """
    path = ROOT / "src" / "cli" / "screens" / "database_manager.py"
    lines = _duplicate_branches(path)

    assert lines, ("дубль ветки в database_manager.py исправлен — "
                   "уберите пункт 1 из web/FRAMEWORK_NOTES.md и этот тест")


def test_framework_notes_stay_honest():
    """Замечания без ссылки на место в коде проверить нельзя — значит, их там нет."""
    notes = (ROOT / "web" / "FRAMEWORK_NOTES.md").read_text(encoding="utf-8")

    for mentioned in ("src/cli/screens/database_manager.py",
                      "src/l1_databases/vector/db.py"):
        assert mentioned in notes
        assert (ROOT / mentioned).exists(), "файл из замечаний исчез: %s" % mentioned


def test_tests_do_not_depend_on_ignored_config_files():
    """
    `settings.yaml`, `interfaces.yaml` и `.env` перечислены в `.gitignore`: в
    свежем клоне и в CI их нет. Тесты, читающие их напрямую, там развалятся —
    а проверить это локально нельзя, рабочие файлы лежат под рукой.
    """
    import re as _re

    web_tests = sorted((ROOT / "tests" / "web").glob("test_*.py"))
    assert web_tests, "тесты консоли не найдены"

    offenders = {}
    for path in web_tests:
        text = path.read_text(encoding="utf-8")
        # интересуют только прямые чтения, не подмены monkeypatch-ем
        hits = _re.findall(r"load_yaml\(cio\.(SETTINGS_FILE|INTERFACES_FILE)\)", text)
        hits += _re.findall(r"shutil\.copy\(cio\.(SETTINGS_FILE|INTERFACES_FILE|ENV_FILE)",
                            text)
        if hits:
            offenders[path.name] = sorted(set(hits))

    assert not offenders, (
        "тесты читают конфиги, которых нет в свежем клоне: %s. "
        "Используйте фикстуры settings_yaml / interfaces_yaml или source_config()"
        % offenders)


def test_console_creates_missing_configs_from_examples():
    """
    Консоль можно открыть до первой настройки. Раньше она падала на чтении:
    рабочих конфигов в свежем клоне нет. Копирование образцов повторяет то, что
    делает мастер настройки CLI.
    """
    from src.web import server as srv

    assert hasattr(cio, "ensure_config_files")
    assert "ensure_config_files" in source("src/web/server.py"), \
        "конфиги не создаются при запуске консоли"

    for _target, example in cio.EXAMPLES:
        assert example.exists(), "образец исчез: %s" % example.name


def test_version_matches_the_framework_source():
    """
    Версия в углу консоли — это версия фреймворка. Читаем её из
    `src/__init__.py` текстом; проверяем, что разбор совпадает с тем, что
    получается импортом.
    """
    import src

    assert cio.framework_version() == src.__version__, \
        "разбор версии разошёлся с самим значением"
    assert cio.framework_version(), "версия не прочиталась"


def test_version_reader_survives_a_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cio, "ROOT_DIR", tmp_path)
    assert cio.framework_version() == ""


def test_fundamental_descriptions_cover_every_drive():
    """
    Перевод описаний должен покрывать те же мотиваторы, что и перевод названий,
    иначе один из них покажется по-английски рядом с русскими.
    """
    keys = {key for key, _title in drives.FUNDAMENTAL_TITLES.values()}

    assert set(drives.FUNDAMENTAL_DESCRIPTIONS) == keys, \
        "перевод описаний разошёлся с составом мотиваторов"
    for key, text in drives.FUNDAMENTAL_DESCRIPTIONS.items():
        assert text and not re.search(r"[A-Za-z]{4,}", text), \
            "описание «%s» осталось на английском" % key


def test_batch_file_lives_with_the_tests():
    """Запускать тесты удобнее оттуда, где они лежат."""
    script = ROOT / "tests" / "web" / "test.bat"

    assert script.exists(), "test.bat не найден рядом с тестами"
    assert not (ROOT / "test.bat").exists(), "остался дубль в корне"

    text = script.read_text(encoding="utf-8")
    assert '%~dp0..\..' in text, "скрипт не переходит в корень проекта"
    assert "pytest tests/web" in text

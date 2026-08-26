# -*- coding: utf-8 -*-
"""
Счётчики трёх баз и необратимая очистка.

Главное здесь — не арифметика, а два запрета:

* очистка невозможна, пока агент запущен. Это правило самого фреймворка
  (`database_manager_screen` отказывается работать при живом агенте), и для
  двух баз из трёх ещё и физика: Qdrant держит `.lock`, Kuzu — исключительную
  блокировку файла;
* заблокированная база не показывается нулём. Ноль означает «пусто», а не
  «не смогли прочитать», и спутать эти два состояния перед кнопкой «Очистить»
  особенно дорого.

Ни один тест не притрагивается к настоящим базам агента: всё делается на
копиях во временном каталоге.
"""

import re
import sqlite3

import pytest

from src.web import agent, database


@pytest.fixture
def storages(tmp_path, monkeypatch):
    """Полный набор хранилищ во временном каталоге, агент считается остановленным."""
    sql_file = tmp_path / "sql" / "db" / "agent.db"
    sql_file.parent.mkdir(parents=True)

    conn = sqlite3.connect(sql_file)
    conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT)")
    conn.execute("CREATE TABLE notes (id TEXT PRIMARY KEY, text TEXT)")
    conn.execute("CREATE TABLE mental_states (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE personality_traits (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE drives (id TEXT PRIMARY KEY, name TEXT, type TEXT)")
    conn.execute("CREATE TABLE ticks (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO tasks VALUES (?,?)", [("t1", "раз"), ("t2", "два")])
    conn.execute("INSERT INTO notes VALUES ('n1','заметка')")
    conn.execute("INSERT INTO mental_states VALUES ('m1','Сэм')")
    conn.execute("INSERT INTO personality_traits VALUES ('p1','ирония')")
    conn.executemany(
        "INSERT INTO drives VALUES (?,?,?)",
        [
            ("d1", "Curiosity", "fundamental"),
            ("d2", "Social", "fundamental"),
            ("d3", "UserCare", "custom"),
        ],
    )
    conn.commit()
    conn.close()

    vector_dir = tmp_path / "vector" / "db"
    for name, rows in (("knowledge", 3), ("thoughts", 1), ("code_ast", 0)):
        storage = vector_dir / "collection" / name / "storage.sqlite"
        storage.parent.mkdir(parents=True)
        vc = sqlite3.connect(storage)
        vc.execute("CREATE TABLE points (id TEXT PRIMARY KEY, point BLOB)")
        vc.executemany(
            "INSERT INTO points VALUES (?,?)", [("p%d" % i, b"x") for i in range(rows)]
        )
        vc.commit()
        vc.close()
    (vector_dir / ".lock").write_text("занято", encoding="utf-8")

    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    (graph_dir / "agent_graph.db").write_bytes(b"kuzu" * 100)

    interfaces = tmp_path / "interfaces"
    (interfaces / "web").mkdir(parents=True)
    (interfaces / "web" / "cookies.json").write_text("{}", encoding="utf-8")

    sandbox = tmp_path / "sandbox"
    (sandbox / "мусор").mkdir(parents=True)
    (sandbox / "мусор" / "файл.txt").write_text("хлам", encoding="utf-8")
    (sandbox / "верхний.txt").write_text("хлам", encoding="utf-8")

    monkeypatch.setattr(database, "SQL_DB_FILE", sql_file)
    monkeypatch.setattr(database, "VECTOR_DB_DIR", vector_dir)
    monkeypatch.setattr(database, "GRAPH_DB_DIR", graph_dir)
    monkeypatch.setattr(database, "GRAPH_DB_FILE", graph_dir / "agent_graph.db")
    monkeypatch.setattr(database, "INTERFACES_DIR", interfaces)
    monkeypatch.setattr(database, "SANDBOX_DIR", sandbox)
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": False})
    database._dir_cache.clear()

    class Storages:
        sql = sql_file
        vector = vector_dir
        graph = graph_dir
        interfaces_dir = interfaces
        sandbox_dir = sandbox

        @staticmethod
        def rows(table):
            conn = sqlite3.connect(sql_file)
            try:
                return conn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
            finally:
                conn.close()

    return Storages


@pytest.fixture
def running_agent(monkeypatch):
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": True})


# ---------------------------------------------------------------- счётчики


def test_counts_every_module(storages):
    counts = database.stats()["sql"]["counts"]

    assert counts["tasks"] == 2
    assert counts["notes"] == 1
    assert counts["mental_states"] == 1
    assert counts["personality_traits"] == 1
    assert counts["drives"] == 3


def test_limits_come_from_settings(storages, sandbox_config):
    """
    «2 из 5» должно сходиться с потолком модуля в settings.yaml, иначе счётчик
    будет противоречить вкладке «Память».
    """
    limits = database.stats()["sql"]["limits"]

    assert limits["tasks"] == 5 and limits["mental_states"] == 10
    assert set(limits) == set(database.SQL_MODULES)


def test_drives_are_split_by_kind(storages):
    """Фундаментальные восстанавливаются из конфига, свои — нет; их нельзя смешивать."""
    assert database.stats()["sql"]["drives"] == {"fundamental": 2, "custom": 1}


def test_vector_counts_are_read_around_the_lock(storages):
    """
    Qdrant держит `.lock` на каталоге, но точки лежат в обычном SQLite. CLI в
    этом случае показывает нули, а мы читаем настоящие числа.
    """
    assert (storages.vector / ".lock").exists(), "проверяем именно случай с блокировкой"
    assert database.stats()["vector"]["counts"] == {
        "knowledge": 3,
        "thoughts": 1,
        "code_ast": 0,
    }


def test_graph_is_marked_locked_while_the_agent_runs(storages, running_agent):
    """
    Kuzu не пустит второй процесс даже на чтение. Показать ноль значило бы
    сказать «граф пуст» перед кнопкой очистки.
    """
    graph = database.stats()["graph"]

    assert graph["locked"] is True
    assert graph["counts"] == {}, "при блокировке цифр быть не должно"
    assert graph["sizeBytes"] > 0, "размер файла виден и при блокировке"


def test_missing_storages_are_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "SQL_DB_FILE", tmp_path / "нет.db")
    monkeypatch.setattr(database, "VECTOR_DB_DIR", tmp_path / "нет")
    monkeypatch.setattr(database, "GRAPH_DB_FILE", tmp_path / "нет.kuzu")
    monkeypatch.setattr(database, "INTERFACES_DIR", tmp_path / "нет")
    monkeypatch.setattr(database, "SANDBOX_DIR", tmp_path / "нет")
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": False})
    database._dir_cache.clear()

    res = database.stats()

    assert res["ok"] is True
    assert res["sql"]["exists"] is False and res["graph"]["exists"] is False


def test_directory_sizes_are_reported(storages):
    dirs = database.stats()["dirs"]

    assert dirs["sandbox"]["files"] == 2, "файлы считаются рекурсивно"
    assert dirs["interfaces"]["sizeBytes"] > 0


# ---------------------------------------------------------------- запрет очистки


@pytest.mark.parametrize(
    "scope",
    ["sql.tasks", "sql.all", "vector.knowledge", "vector.all", "graph.all", "interfaces.all"],
)
def test_wipe_refuses_while_the_agent_runs(storages, running_agent, scope):
    """
    Самый важный запрет: агент держит базы открытыми, а состояние — в памяти.
    Правка под ним разошлась бы с тем, что агент считает правдой.
    """
    res = database.wipe(scope)

    assert res["ok"] is False and res["needsStop"] is True
    assert storages.rows("tasks") == 2, "данные тронуты вопреки отказу"
    assert storages.sql.exists() and storages.graph.exists()


def test_unknown_scope_is_rejected(storages):
    res = database.wipe("sql.всё-подряд")

    assert res["ok"] is False and "неизвестная" in res["error"]
    assert storages.rows("tasks") == 2


def test_unknown_scope_is_rejected_before_the_agent_check(storages, running_agent):
    """Опечатка в области не должна маскироваться сообщением про запущенного агента."""
    res = database.wipe("нет.такого")

    assert res.get("needsStop") is None


# ---------------------------------------------------------------- очистка


def test_wipes_one_table_and_leaves_the_rest(storages):
    res = database.wipe("sql.tasks")

    assert res["ok"] is True and "2" in res["detail"]
    assert storages.rows("tasks") == 0
    assert storages.rows("notes") == 1, "задета соседняя таблица"
    assert storages.rows("drives") == 3


def test_wiping_drives_removes_both_kinds(storages):
    """
    Фундаментальные агент воссоздаст из settings.yaml при следующем запуске,
    свои исчезнут навсегда — это и есть «сброс мотиваторов».
    """
    database.wipe("sql.drives")

    assert storages.rows("drives") == 0


def test_wipes_the_whole_relational_database(storages):
    res = database.wipe("sql.all")

    assert res["ok"] is True
    assert not storages.sql.exists(), "файл базы должен быть удалён"


def test_wipes_the_whole_vector_database(storages):
    database.wipe("vector.all")

    assert not storages.vector.exists()


def test_wipes_the_whole_graph(storages):
    database.wipe("graph.all")

    assert not storages.graph.exists()


def test_wiping_empty_storage_is_not_an_error(storages):
    database.wipe("sql.all")
    res = database.wipe("sql.all")

    assert res["ok"] is True and "пуст" in res["detail"]


def test_interfaces_wipe_restores_the_sandbox_skeleton(storages):
    """
    Песочницу нельзя просто снести: агент ждёт там папку загрузок и шину
    событий. Логика повторяет `_clear_sandbox` из CLI.
    """
    res = database.wipe("interfaces.all")

    assert res["ok"] is True
    assert not storages.interfaces_dir.exists(), "кэш интерфейсов не удалён"
    assert not (storages.sandbox_dir / "мусор").exists()
    assert not (storages.sandbox_dir / "верхний.txt").exists()

    assert (storages.sandbox_dir / "_system" / "download").is_dir()
    assert (storages.sandbox_dir / "_system" / ".jawl_events").is_dir()


def test_stats_are_fresh_after_a_wipe(storages):
    """Размеры каталогов кэшируются — после очистки кэш обязан сброситься."""
    database.stats()
    database.wipe("interfaces.all")

    assert database.stats()["dirs"]["interfaces"]["exists"] is False


# ---------------------------------------------- согласованность с фреймворком и разметкой


def _cli_source():
    from src.web import config_io as cio

    return (cio.ROOT_DIR / "src" / "cli" / "screens" / "database_manager.py").read_text(
        encoding="utf-8"
    )


def test_sandbox_skeleton_matches_the_cli():
    """
    `_clear_sandbox` продублирован, а не импортирован: модуль CLI тянет за собой
    questionary и весь интерфейс командной строки. Дубликат обязан не разойтись
    с оригиналом.
    """
    source = _cli_source()

    for piece in ('"_system"', '"download"', '".jawl_events"', "framework_api.py"):
        assert piece in source, "состав песочницы в CLI изменился: %s" % piece


def test_storage_paths_match_the_cli():
    """Пути к базам заданы в двух местах — разъедутся, и консоль почистит не то."""
    source = _cli_source()

    for piece in ('"sql" / "db" / "agent.db"', '"vector" / "db"', '"graph"'):
        assert piece in source, "путь к базе в CLI изменился: %s" % piece


def test_graph_node_table_matches_the_schema():
    """Имя вершины берётся из схемы графа; разойдётся — счётчик станет нулём."""
    from src.l1_databases.graph import schema

    assert database.GRAPH_NODE_TABLE == schema.GRAPH_NODE_TABLE
    assert database.CODE_NODE_TABLE == schema.CODE_NODE_TABLE


def test_every_button_scope_is_known_to_the_server(index_html):
    """Кнопка есть, а сервер про область не знает — очистка молча не сработает."""
    scopes = set(re.findall(r'data-scope="([^"]+)"', index_html))

    assert scopes, "кнопки очистки исчезли из разметки"
    unknown = sorted(scopes - set(database.scopes()))
    assert not unknown, "сервер не знает области: %s" % unknown


def test_every_sql_module_has_a_button(index_html):
    """Обратное: модуль описан на сервере, но очистить его нечем."""
    scopes = set(re.findall(r'data-scope="([^"]+)"', index_html))
    missing = ["sql.%s" % key for key in database.SQL_MODULES if "sql.%s" % key not in scopes]

    assert not missing, "нет кнопок для: %s" % missing


def test_wipe_buttons_are_locked_until_the_agent_state_is_known(index_html):
    """
    До ответа сервера неизвестно, запущен ли агент. Кнопка необратимого
    действия не должна быть доступна на этом промежутке.
    """
    buttons = re.findall(r'<button class="btn danger wipe"[^>]*>', index_html)

    assert buttons, "кнопки очистки исчезли"
    unlocked = [b for b in buttons if "disabled" not in b]
    assert not unlocked, "не заперты: %s" % unlocked


# ------------------------------------------------- очистка настоящих хранилищ


@pytest.fixture
def real_qdrant(tmp_path, monkeypatch):
    """Настоящая локальная база Qdrant: путь удаления точек стоит проверять по-честному."""
    from qdrant_client import QdrantClient, models

    path = tmp_path / "vector" / "db"
    client = QdrantClient(path=str(path))
    client.create_collection(
        "knowledge",
        vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE),
    )
    client.create_collection(
        "thoughts", vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE)
    )
    client.upsert(
        "knowledge",
        points=[
            models.PointStruct(id=i, vector=[0.1] * 4, payload={"tags": ["память"]})
            for i in range(5)
        ],
    )
    client.upsert(
        "thoughts",
        points=[models.PointStruct(id=1, vector=[0.2] * 4, payload={"tags": ["мысль"]})],
    )
    client.close()

    monkeypatch.setattr(database, "VECTOR_DB_DIR", path)
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": False})
    return path


def test_vector_collection_is_emptied_without_losing_its_schema(real_qdrant):
    """
    CLI пересоздаёт коллекцию, подставляя `vector_size` из settings.yaml. Если
    размерность в конфиге успели поменять, пересозданная коллекция разойдётся с
    накопленными эмбеддингами. Удаляем точки — схему выводить заново не нужно.
    """
    from qdrant_client import QdrantClient, models

    res = database.wipe("vector.knowledge")
    assert res["ok"] is True and "5" in res["detail"]

    client = QdrantClient(path=str(real_qdrant))
    try:
        assert client.count("knowledge").count == 0
        assert client.count("thoughts").count == 1, "задета соседняя коллекция"
        assert client.collection_exists("knowledge"), "коллекция удалена вместе с точками"

        # схема должна остаться ровно той, что создал агент
        params = client.get_collection("knowledge").config.params.vectors
        assert params.size == 4, "размерность выведена заново"
        assert params.distance == models.Distance.COSINE
    finally:
        client.close()


@pytest.fixture
def real_kuzu(tmp_path, monkeypatch):
    """Настоящий граф Kuzu с вершинами и связью между ними."""
    kuzu = pytest.importorskip("kuzu")

    path = tmp_path / "graph" / "agent_graph.db"
    path.parent.mkdir(parents=True)

    db = kuzu.Database(str(path))
    conn = kuzu.Connection(db)
    conn.execute("CREATE NODE TABLE Concept(id STRING, name STRING, PRIMARY KEY(id))")
    conn.execute("CREATE REL TABLE IS_A(FROM Concept TO Concept)")
    conn.execute("CREATE (:Concept {id:'1', name:'кот'})")
    conn.execute("CREATE (:Concept {id:'2', name:'животное'})")
    conn.execute("MATCH (a:Concept {id:'1'}), (b:Concept {id:'2'}) CREATE (a)-[:IS_A]->(b)")
    conn.close()
    db.close()

    monkeypatch.setattr(database, "GRAPH_DB_DIR", path.parent)
    monkeypatch.setattr(database, "GRAPH_DB_FILE", path)
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": False})
    return path


def test_graph_is_counted_when_the_agent_is_stopped(real_kuzu):
    graph = database.stats()["graph"]

    assert graph["locked"] is False
    assert graph["counts"]["concepts"] == 2
    assert graph["counts"]["code"] is None, "таблицы графа кода нет — не выдумываем ноль"


def test_graph_concepts_wipe_takes_relations_with_them(real_kuzu):
    """Kuzu не даст удалить вершину со связями — нужен DETACH DELETE."""
    import kuzu

    res = database.wipe("graph.concepts")
    assert res["ok"] is True and "2" in res["detail"]

    db = kuzu.Database(str(real_kuzu), read_only=True)
    conn = kuzu.Connection(db)
    try:
        assert conn.execute("MATCH (n:Concept) RETURN count(n)").get_next()[0] == 0
        assert conn.execute("MATCH ()-[e:IS_A]->() RETURN count(e)").get_next()[0] == 0
    finally:
        conn.close()
        db.close()


# ---------------------------------------------------------------- дескрипторы


def test_reading_stats_does_not_hold_the_files(storages):
    """
    Воспроизводит настоящую ошибку: «WinError 32 — файл занят другим процессом»
    при очистке векторной базы.

    Причина была не в агенте, а в самой консоли. `with sqlite3.connect(...)`
    закрывает транзакцию, но не файл, а счётчики опрашиваются раз в несколько
    секунд — дескрипторы копились, и Windows отказывался удалять каталог.
    """
    for _ in range(5):
        database.stats()

    res = database.wipe("vector.all")

    assert res["ok"] is True, "каталог не удалился: %s" % res.get("error")
    assert not storages.vector.exists()


def test_reading_stats_does_not_hold_the_relational_file(storages):
    for _ in range(5):
        database.stats()

    res = database.wipe("sql.all")

    assert res["ok"] is True, "файл базы не удалился: %s" % res.get("error")
    assert not storages.sql.exists()


def test_listing_drives_does_not_hold_the_database(storages, monkeypatch):
    """Та же утечка была и в опросе шкал мотиваторов — раз в десять секунд."""
    from src.web import drives

    monkeypatch.setattr(drives, "DB_FILE", storages.sql)
    for _ in range(5):
        drives.list_drives()

    res = database.wipe("sql.all")

    assert res["ok"] is True, "шкалы держат файл: %s" % res.get("error")


def test_busy_file_gives_a_readable_answer(storages, monkeypatch):
    """
    Windows не даёт удалить занятый файл. Пользователь должен получить понятное
    объяснение, а не сырое «PermissionError: [WinError 32]».
    """

    def always_busy(path, *a, **kw):
        raise PermissionError(32, "файл занят другим процессом")

    monkeypatch.setattr(database.shutil, "rmtree", always_busy)
    monkeypatch.setattr(database, "UNLOCK_PAUSE_SEC", 0.001)
    monkeypatch.setattr(database, "UNLOCK_ATTEMPTS", 2)

    res = database.wipe("vector.all")

    assert res["ok"] is False
    assert res.get("busy") is True
    assert "занят другим процессом" in res["error"]
    assert "PermissionError" not in res["error"], "наружу торчит имя исключения"
    assert "повторите" in res["error"], "нет подсказки, что делать"


def test_removal_survives_a_lock_that_releases(storages, monkeypatch):
    """
    Только что остановленный агент отпускает файлы не мгновенно. Одна неудачная
    попытка не должна проваливать всю очистку.
    """
    calls = {"n": 0}
    real = database.shutil.rmtree

    def flaky(path, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(32, "занято")
        return real(path, *a, **kw)

    monkeypatch.setattr(database.shutil, "rmtree", flaky)
    monkeypatch.setattr(database, "UNLOCK_PAUSE_SEC", 0.01)

    res = database.wipe("vector.all")

    assert res["ok"] is True and calls["n"] == 2, "повтора не было"
    assert not storages.vector.exists()


# ---------------------------------------------------------------- модели эмбеддингов


@pytest.fixture
def embeddings(tmp_path, monkeypatch):
    """Кэш весов с двумя моделями: используемой и оставшейся от прежней настройки."""
    root = tmp_path / "embeddings"
    for folder, size in (
        ("models--qdrant--multilingual-e5-large-onnx", 300),
        ("models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q", 900),
    ):
        blobs = root / folder / "blobs"
        blobs.mkdir(parents=True)
        (blobs / "model.onnx").write_bytes(b"x" * size)
    (root / ".locks").mkdir()  # служебный каталог huggingface
    (root / "CACHEDIR.TAG").write_text("tag", encoding="utf-8")

    monkeypatch.setattr(database, "EMBEDDINGS_DIR", root)
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": False})
    monkeypatch.setattr(
        database,
        "_settings",
        lambda: {
            "system": {"db": {"vector": {"embedding_model": "intfloat/multilingual-e5-large"}}}
        },
    )
    database._dir_cache.clear()
    return root


def test_lists_downloaded_models(embeddings):
    info = database.stats()["embeddings"]

    assert [m["dir"] for m in info["models"]] == [
        "models--qdrant--multilingual-e5-large-onnx",
        "models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q",
    ], "служебные каталоги не должны попадать в список"
    assert info["sizeBytes"] == 1200


def test_active_model_is_marked(embeddings):
    """
    Видно, какие веса можно убрать. Имя в настройках и каталог на диске
    различаются: fastembed качает свою ONNX-сборку.
    """
    models = {m["dir"]: m for m in database.stats()["embeddings"]["models"]}

    assert models["models--qdrant--multilingual-e5-large-onnx"]["active"] is True
    assert (
        models["models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"]["active"]
        is False
    )


def test_cache_folders_are_named_by_the_model(embeddings):
    """Каталог `models--qdrant--…` сам по себе ничего не говорит пользователю."""
    titles = [m["title"] for m in database.stats()["embeddings"]["models"]]

    assert "intfloat/multilingual-e5-large" in titles
    assert "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" in titles


def test_missing_active_model_is_reported(embeddings, monkeypatch):
    """Модель в настройках сменили, а весов под неё ещё нет — это надо сказать."""
    monkeypatch.setattr(
        database,
        "_settings",
        lambda: {"system": {"db": {"vector": {"embedding_model": "какая-то/другая"}}}},
    )

    info = database.stats()["embeddings"]
    assert info["activeDownloaded"] is False
    assert info["activeModel"] == "какая-то/другая"


def test_wipes_one_model_and_leaves_the_other(embeddings):
    scope = "embeddings.models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
    res = database.wipe(scope)

    assert res["ok"] is True
    assert not (
        embeddings / "models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
    ).exists()
    assert (embeddings / "models--qdrant--multilingual-e5-large-onnx").exists()


def test_wipes_the_whole_model_cache(embeddings):
    res = database.wipe("embeddings.all")

    assert res["ok"] is True
    assert not embeddings.exists()


@pytest.mark.parametrize(
    "scope",
    [
        "embeddings.",
        "embeddings.нет-такой-модели",
        "embeddings...",
        "embeddings.../../config",
        "embeddings.models--qdrant--multilingual-e5-large-onnx/blobs",
        "embeddings..locks",
    ],
)
def test_model_scope_cannot_escape_the_cache(embeddings, scope):
    """
    Имена моделей приходят с клиента и не перечислены заранее. Проверяем, что
    выйти за пределы каталога кэша нельзя.
    """
    res = database.wipe(scope)

    assert res["ok"] is False, "принята подозрительная область: %s" % scope
    assert embeddings.exists()
    assert (embeddings / "models--qdrant--multilingual-e5-large-onnx").exists()


def test_model_wipe_refuses_while_the_agent_runs(embeddings, running_agent):
    scope = "embeddings.models--qdrant--multilingual-e5-large-onnx"
    res = database.wipe(scope)

    assert res["ok"] is False and res["needsStop"] is True
    assert (embeddings / "models--qdrant--multilingual-e5-large-onnx").exists()


def test_model_scope_label_is_readable(embeddings):
    label = database.scope_label("embeddings.models--qdrant--multilingual-e5-large-onnx")
    assert "модель эмбеддингов" in label


def test_markup_has_a_place_for_the_model_list(index_html):
    """Список строится на лету — в разметке должен быть контейнер под него."""
    assert 'id="embList"' in index_html
    assert "Скачанные модели эмбеддингов" in index_html

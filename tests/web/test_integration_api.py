# -*- coding: utf-8 -*-
"""
Сквозная проверка HTTP-слоя: браузер -> сервер -> файлы -> браузер.

Работает по копиям конфигов (фикстура sandbox_config), настоящие файлы
репозитория не трогаются.
"""

import asyncio
import io
import json

import pytest
import yaml
from aiohttp.test_utils import TestClient, TestServer

from src.web import config_io as cio
from src.web import schema
from src.web.server import make_app


@pytest.fixture
async def client(sandbox_config):
    async with TestClient(TestServer(make_app())) as cl:
        yield cl


@pytest.fixture
async def guarded_client(sandbox_config):
    """Сервер с токеном — как при запуске не на localhost."""
    async with TestClient(TestServer(make_app(token="s3cret"))) as cl:
        yield cl


# ---------------------------------------------------------------- чтение

async def test_get_returns_every_mapped_field(client):
    resp = await client.get("/api/config")
    assert resp.status == 200
    body = await resp.json()

    assert body["ok"] is True
    known = (set(schema.SETTINGS_FIELDS) | set(schema.INTERFACES_FIELDS)
             | set(schema.ENV_FIELDS))
    assert set(body["values"]) == known
    assert set(body["lists"]) == (set(schema.SETTINGS_LISTS) | set(schema.ENV_LISTS)
                                  | set(schema.INTERFACES_LISTS)
                                  | set(schema.INTERFACES_OBJECT_LISTS))


async def test_get_preserves_python_types(client):
    body = await (await client.get("/api/config")).json()
    values = body["values"]

    assert isinstance(values["settings:llm.temperature"], float)
    assert isinstance(values["settings:llm.max_react_steps"], int)
    assert isinstance(values["settings:llm.is_multimodal"], bool)
    assert isinstance(values["settings:identity.agent_name"], str)


# ---------------------------------------------------------------- запись

async def test_put_writes_scalars_lists_and_env(client, sandbox_config):
    payload = {
        "values": {
            "settings:identity.agent_name": "Тесс",
            "settings:llm.temperature": 0.42,
            "settings:system.db.sql.drives.fundamental.social.decay.rate": 15.5,
            "settings:system.subconscious.patterns.forgetting.enabled": False,
            "env:LLM_API_URL": "https://example.dev/v1/",
        },
        "lists": {
            "modelList": ["alpha", "beta"],
            "keyList": ["k1", "k2"],
        },
    }
    body = await (await client.put("/api/config", json=payload)).json()

    assert body["ok"] is True
    assert body["unknown"] == []
    assert set(body["written"]) == {"config/settings.yaml", ".env"}

    data = yaml.safe_load(io.open(sandbox_config.settings_path, encoding="utf-8"))
    assert data["identity"]["agent_name"] == "Тесс"
    assert data["llm"]["temperature"] == 0.42
    assert data["llm"]["available_models"] == ["alpha", "beta"]
    assert data["system"]["db"]["sql"]["drives"]["fundamental"]["social"]["decay"]["rate"] == 15.5
    assert data["system"]["subconscious"]["patterns"]["forgetting"]["enabled"] is False

    env = sandbox_config.env_text()
    assert 'LLM_API_URL="https://example.dev/v1/"' in env
    assert 'LLM_API_KEY_1="k1"' in env and 'LLM_API_KEY_2="k2"' in env


async def test_round_trip_returns_what_was_written(client):
    await client.put("/api/config", json={
        "values": {"settings:system.heartbeat_interval": 333}, "lists": {}})
    body = await (await client.get("/api/config")).json()
    assert body["values"]["settings:system.heartbeat_interval"] == 333


async def test_put_reports_unknown_keys_instead_of_failing(client):
    body = await (await client.put("/api/config", json={
        "values": {"settings:llm.no_such_key": 1}, "lists": {}})).json()
    assert body["ok"] is True
    assert "settings:llm.no_such_key" in body["unknown"]


async def test_put_touches_nothing_when_payload_is_empty(client, sandbox_config):
    before = sandbox_config.settings_text()
    body = await (await client.put("/api/config", json={"values": {}, "lists": {}})).json()
    assert body["written"] == []
    assert sandbox_config.settings_text() == before


async def test_broken_json_gives_400(client):
    resp = await client.put("/api/config", data="не json",
                            headers={"Content-Type": "application/json"})
    assert resp.status == 400


# ---------------------------------------------------------------- статика и доступ

async def test_index_and_assets_are_served(client):
    assert (await client.get("/")).status == 200
    assert (await client.get("/styles.css")).status == 200
    assert (await client.get("/console.js")).status == 200


async def test_api_requires_token_when_one_is_set(guarded_client):
    """Без токена наружу отдавать .env нельзя."""
    assert (await guarded_client.get("/api/config")).status == 401

    ok = await guarded_client.get("/api/config", headers={"X-Console-Token": "s3cret"})
    assert ok.status == 200

    ok_query = await guarded_client.get("/api/config?token=s3cret")
    assert ok_query.status == 200


async def test_static_stays_open_with_token(guarded_client):
    """Токен закрывает данные, а не саму страницу — иначе её нечем открыть."""
    assert (await guarded_client.get("/")).status == 200


# ---------------------------------------------------------------- интерфейсы

async def test_put_writes_interfaces_scalars_and_lists(client, sandbox_config):
    payload = {
        "values": {
            "interfaces:host.os.enabled": True,
            "interfaces:host.os.access_level": 2,
            "interfaces:web.hooks.port": 9090,
            "interfaces:web.search.search_engine": "tavily",
            "interfaces:voice.tts.cloud.edge.rate": "+15%",
            "env:GITHUB_TOKEN": "ghp_test",
        },
        "lists": {
            "lstExcludeDirs": ["venv", "dist"],
            "lstElevenVoices": ["voice-A"],
            "lstFeeds": [
                {"name": "Habr", "url": "https://habr.com/x"},
                {"name": "arXiv", "url": "https://arxiv.org/y"},
            ],
        },
    }
    body = await (await client.put("/api/config", json=payload)).json()

    assert body["ok"] is True and body["unknown"] == []
    assert set(body["written"]) == {"config/interfaces.yaml", ".env"}

    data = yaml.safe_load(io.open(sandbox_config.interfaces_path, encoding="utf-8"))
    assert data["host"]["os"]["enabled"] is True
    assert data["host"]["os"]["access_level"] == 2
    assert data["web"]["hooks"]["port"] == 9090
    assert data["web"]["search"]["search_engine"] == "tavily"
    assert data["voice"]["tts"]["cloud"]["edge"]["rate"] == "+15%"
    assert data["code_graph"]["exclude_dirs"] == ["venv", "dist"]
    assert data["voice"]["tts"]["cloud"]["elevenlabs"]["available_voices"] == ["voice-A"]
    assert data["web"]["rss"]["feeds"] == [
        {"name": "Habr", "url": "https://habr.com/x"},
        {"name": "arXiv", "url": "https://arxiv.org/y"},
    ]


async def test_interfaces_write_touches_only_changed_lines(client, sandbox_config):
    """Комментарии и отступы файла должны пережить запись."""
    before = sandbox_config.interfaces_text().replace("\r\n", "\n").split("\n")

    await client.put("/api/config", json={
        "values": {"interfaces:web.hooks.port": 9090}, "lists": {}})

    after = sandbox_config.interfaces_text().replace("\r\n", "\n").split("\n")
    diff = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(diff) == 1, "затронуто строк: %d" % len(diff)
    assert "9090" in diff[0][1]


async def test_empty_list_collapses_to_brackets(client, sandbox_config):
    """Пустой список пишется как `key: []`, иначе получится ключ без значения."""
    await client.put("/api/config", json={
        "values": {}, "lists": {"lstEdgeVoices": []}})

    text = sandbox_config.interfaces_text()
    assert "available_voices: []" in text

    data = yaml.safe_load(io.open(sandbox_config.interfaces_path, encoding="utf-8"))
    assert data["voice"]["tts"]["cloud"]["edge"]["available_voices"] == []


async def test_list_items_keep_their_quoting_style(client, sandbox_config):
    """В exclude_dirs элементы записаны в кавычках — стиль сохраняем."""
    await client.put("/api/config", json={
        "values": {}, "lists": {"lstExcludeDirs": ["venv", "build"]}})
    text = sandbox_config.interfaces_text()
    assert '- "venv"' in text and '- "build"' in text


async def test_interfaces_stay_valid_yaml_after_write(client, sandbox_config):
    await client.put("/api/config", json={
        "values": {"interfaces:meta.access_level": 3},
        "lists": {"lstFeeds": [{"name": "N", "url": "U"}]},
    })
    data = yaml.safe_load(io.open(sandbox_config.interfaces_path, encoding="utf-8"))
    assert data["meta"]["access_level"] == 3


# ---------------------------------------------------------------- управление агентом

async def test_agent_status_endpoint(client, monkeypatch):
    from src.web import agent
    monkeypatch.setattr(agent, "status",
                        lambda: {"ok": True, "running": True, "starting": False,
                                 "pid": 42, "uptimeSec": 7})

    body = await (await client.get("/api/agent/status")).json()
    assert body["running"] is True and body["pid"] == 42


async def test_agent_start_endpoint_reports_failure_with_409(client, monkeypatch):
    from src.web import agent
    monkeypatch.setattr(agent, "start",
                        lambda: {"ok": False, "error": "агент уже запущен"})

    resp = await client.post("/api/agent/start")
    assert resp.status == 409
    assert "уже запущен" in (await resp.json())["error"]


async def test_agent_start_and_stop_endpoints(client, monkeypatch):
    from src.web import agent
    monkeypatch.setattr(agent, "start", lambda: {"ok": True, "pid": 100})
    monkeypatch.setattr(agent, "stop", lambda: {"ok": True, "forced": False})

    assert (await (await client.post("/api/agent/start")).json())["pid"] == 100
    assert (await (await client.post("/api/agent/stop")).json())["forced"] is False


async def test_agent_routes_are_closed_by_token(guarded_client):
    """Запуск и остановка агента — не то, что открывают без токена."""
    assert (await guarded_client.get("/api/agent/status")).status == 401
    assert (await guarded_client.post("/api/agent/start")).status == 401
    assert (await guarded_client.post("/api/agent/stop")).status == 401


# ---------------------------------------------------------------- журнал

@pytest.fixture
def log_file(tmp_path, monkeypatch):
    from src.web import logs as logsrc
    path = tmp_path / "main.log"
    monkeypatch.setattr(logsrc, "LOG_FILE", path)
    return path


def _append(path, text, mode="a"):
    with io.open(path, mode, encoding="utf-8", newline="") as fh:
        fh.write(text)


async def test_logs_tail_endpoint(client, log_file):
    _append(log_file, "2026-08-25 00:00:00.000 - JAWL - INFO - [System] Старт.\n", "w")

    body = await (await client.get("/api/logs")).json()
    assert body["ok"] is True
    assert "[System] Старт." in body["text"]
    assert body["offset"] == log_file.stat().st_size


async def test_logs_endpoint_reports_missing_file(client, log_file):
    """До первого запуска агента журнала нет — это не ошибка."""
    body = await (await client.get("/api/logs")).json()
    assert body["ok"] is True
    assert body["missing"] is True
    assert body["text"] == ""


async def test_logs_stream_delivers_new_lines(client, log_file):
    """Дозапись должна доехать до подписчика, а старое — не прийти повторно."""
    _append(log_file, "2026-08-25 00:00:00.000 - JAWL - INFO - [System] Старое.\n", "w")
    offset = log_file.stat().st_size

    resp = await client.get("/api/logs/stream?offset=%d" % offset)
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")

    _append(log_file, "2026-08-25 00:00:05.000 - JAWL - INFO - [System] Новое.\n")

    payload = None
    for _ in range(8):
        line = await asyncio.wait_for(resp.content.readline(), timeout=5)
        text = line.decode("utf-8").strip()
        if text.startswith("data: "):
            payload = json.loads(text[len("data: "):])
            break

    resp.close()

    assert payload is not None, "поток не прислал новую строку"
    assert "[System] Новое." in payload["text"]
    assert "Старое" not in payload["text"], "старое пришло повторно"
    assert payload["offset"] == log_file.stat().st_size


async def test_logs_download_sends_the_file(client, log_file):
    _append(log_file, "2026-08-25 00:00:00.000 - JAWL - INFO - [System] Строка.\n", "w")

    resp = await client.get("/api/logs/download")
    assert resp.status == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "main.log" in resp.headers["Content-Disposition"]
    assert "[System] Строка." in (await resp.text())


async def test_logs_download_404_without_file(client, log_file):
    assert (await client.get("/api/logs/download")).status == 404


async def test_log_routes_are_closed_by_token(guarded_client):
    assert (await guarded_client.get("/api/logs")).status == 401
    assert (await guarded_client.get("/api/logs/stream")).status == 401
    assert (await guarded_client.get("/api/logs/download")).status == 401


# ---------------------------------------------------------------- мотиваторы

@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    import sqlite3
    from src.web import drives as drivesrc

    path = tmp_path / "agent.db"
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE drives (
            id TEXT PRIMARY KEY, name TEXT, type TEXT, description TEXT,
            decay_rate REAL, decay_interval_sec INTEGER,
            last_satisfied_at TEXT, recent_reflections TEXT
        )""")
    conn.executemany("INSERT INTO drives VALUES (?,?,?,?,?,?,?,?)", [
        ("a1", "Curiosity", "fundamental", "любознательность", 12.0, 1200,
         "2026-08-25 11:40:00.000000", "[]"),
        ("c1", "UserCare", "custom", "забота о пользователе", 10.0, 900,
         "2026-08-25 11:50:00.000000", "[]"),
    ])
    conn.commit()
    conn.close()
    monkeypatch.setattr(drivesrc, "DB_FILE", path)
    return path


async def test_drives_endpoint_lists_both_kinds(client, agent_db):
    body = await (await client.get("/api/drives")).json()

    assert body["ok"] is True
    kinds = {d["type"] for d in body["drives"]}
    assert kinds == {"fundamental", "custom"}

    custom = next(d for d in body["drives"] if d["type"] == "custom")
    assert custom["title"] == "UserCare"
    assert custom["deficit"] >= 0


async def test_drives_endpoint_updates_custom(client, agent_db):
    import sqlite3

    body = await (await client.put("/api/drives", json={
        "updates": {"c1": {"decayRate": 20.0, "decayIntervalSec": 1800}}})).json()
    assert body["ok"] is True and body["updated"] == ["c1"]

    row = sqlite3.connect(agent_db).execute(
        "SELECT decay_rate, decay_interval_sec FROM drives WHERE id='c1'").fetchone()
    assert row == (20.0, 1800)


async def test_drives_endpoint_protects_fundamental(client, agent_db):
    import sqlite3

    body = await (await client.put("/api/drives", json={
        "updates": {"a1": {"decayRate": 99.0}}})).json()
    assert body["updated"] == []

    row = sqlite3.connect(agent_db).execute(
        "SELECT decay_rate FROM drives WHERE id='a1'").fetchone()
    assert row[0] == 12.0


async def test_drives_broken_json_gives_400(client, agent_db):
    resp = await client.put("/api/drives", data="не json",
                            headers={"Content-Type": "application/json"})
    assert resp.status == 400


async def test_drive_routes_are_closed_by_token(guarded_client):
    assert (await guarded_client.get("/api/drives")).status == 401
    assert (await guarded_client.put("/api/drives", json={})).status == 401


# ---------------------------------------------------------------- такт

async def test_tick_route_answers_with_a_state(client):
    """Шапка опрашивает /api/tick раз в полторы секунды — маршрут должен быть."""
    body = await (await client.get("/api/tick")).json()

    assert body["ok"] is True
    for key in ("phase", "step", "maxSteps", "wakeInSec", "intervalSec",
                "continuous", "activity", "events", "seq"):
        assert key in body, "в ответе нет поля %s" % key
    assert body["phase"] in ("wake", "sleep", "off", "unknown")


async def test_tick_reader_advances_between_requests(client, tmp_path, monkeypatch):
    """
    Разбор держит смещение в журнале между запросами. Если бы состояние
    создавалось заново на каждый запрос, шапка теряла бы всплески.
    """
    from src.web import logs, tick

    log_file = tmp_path / "main.log"
    log_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(logs, "LOG_FILE", log_file)
    monkeypatch.setattr(tick, "_watcher", None)

    first = await (await client.get("/api/tick")).json()

    stamp = "2026-08-25 12:00:00.000"
    log_file.write_text(
        "%s - JAWL.Agent - INFO - [ReAct] Reasoning cycle initialized. "
        "Reason: HEARTBEAT (LLM Model: m).\n"
        "%s - JAWL.Agent - INFO - [ReAct] Step 4/8.\n" % (stamp, stamp),
        encoding="utf-8")

    second = await (await client.get("/api/tick")).json()

    assert first["step"] == 0 and second["step"] == 4
    assert second["seq"] > first["seq"], "новые строки должны дать всплеск"


# ---------------------------------------------------------------- база данных

async def test_db_stats_route(client):
    body = await (await client.get("/api/db/stats")).json()

    assert body["ok"] is True
    for key in ("agentRunning", "sql", "vector", "graph", "dirs"):
        assert key in body, "в ответе нет раздела %s" % key


async def test_db_wipe_refuses_while_the_agent_runs(client, monkeypatch):
    """Отказ должен быть машиночитаемым: интерфейс по нему предлагает остановить агента."""
    from src.web import agent

    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": True})
    resp = await client.post("/api/db/wipe", json={"scope": "sql.tasks"})
    body = await resp.json()

    assert resp.status == 409
    assert body["ok"] is False and body["needsStop"] is True


async def test_db_wipe_rejects_unknown_scope(client, monkeypatch):
    from src.web import agent

    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": False})
    resp = await client.post("/api/db/wipe", json={"scope": "выдумка"})

    assert resp.status == 400
    assert (await resp.json())["ok"] is False


async def test_db_wipe_needs_a_body(client):
    resp = await client.post("/api/db/wipe", data="не json")
    assert resp.status == 400


async def test_db_routes_are_closed_by_token(guarded_client):
    """Очистка баз — необратимое действие: без токена её быть не должно."""
    assert (await guarded_client.get("/api/db/stats")).status == 401
    assert (await guarded_client.post("/api/db/wipe", json={"scope": "sql.tasks"})).status == 401


async def test_db_wipe_goes_through_end_to_end(client, tmp_path, monkeypatch):
    """
    Полный путь: запрос → проверка агента → правка хранилища → ответ.
    Работаем по временной копии, настоящие базы агента не трогаем.
    """
    import sqlite3

    from src.web import agent, database

    db_file = tmp_path / "agent.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO tasks VALUES (?)", [("a",), ("b",), ("c",)])
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "SQL_DB_FILE", db_file)
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": False})

    body = await (await client.post("/api/db/wipe", json={"scope": "sql.tasks"})).json()

    assert body["ok"] is True
    assert body["label"] == "задачи", "в ответе не человеческое имя области"
    assert "3" in body["detail"]

    left = sqlite3.connect(db_file).execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    assert left == 0


# ---------------------------------------------------------------- чат

async def test_chat_returns_history_and_status(client):
    body = await (await client.get("/api/chat")).json()

    assert body["ok"] is True
    assert isinstance(body["history"], list)
    assert body["agentName"], "реплики агента подписывать нечем"
    assert body["status"]["state"] in ("idle", "connecting", "online", "offline")


async def test_chat_send_refuses_without_connection(client, monkeypatch):
    """Пока терминал агента не поднят, доставить сообщение некуда."""
    from src.web import chat

    monkeypatch.setattr(chat, "_bridge", chat.ChatBridge())
    resp = await client.post("/api/chat", json={"text": "привет"})
    body = await resp.json()

    assert resp.status == 409
    assert body["ok"] is False and body["offline"] is True


async def test_chat_send_rejects_empty_text(client, monkeypatch):
    from src.web import chat

    monkeypatch.setattr(chat, "_bridge", chat.ChatBridge())
    resp = await client.post("/api/chat", json={"text": "   "})

    assert resp.status == 400
    assert (await resp.json())["ok"] is False


async def test_chat_send_needs_a_body(client):
    assert (await client.post("/api/chat", data="не json")).status == 400


async def test_chat_stream_reports_state_and_releases(client, monkeypatch):
    """
    Подписка на поток означает для агента «оператор открыл терминал». Она обязана
    сниматься при обрыве, иначе агент будет считать, что за ним смотрят.
    """
    from src.web import chat

    link = chat.ChatBridge()
    monkeypatch.setattr(chat, "_bridge", link)
    monkeypatch.setattr(chat, "PORT_FILE", tmp_missing_port())

    resp = await client.get("/api/chat/stream")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")

    chunk = await resp.content.readuntil(b"\n\n")
    assert b"data:" in chunk

    resp.close()
    await asyncio.sleep(0.2)
    assert link.status()["watchers"] == 0, "подписка не снялась после обрыва"


def tmp_missing_port():
    """Путь к несуществующему файлу порта: тест не должен трогать живого агента."""
    from src.web import config_io as cio
    return cio.ROOT_DIR / "нет-такого-файла.port"


async def test_chat_routes_are_closed_by_token(guarded_client):
    """Чат управляет агентом: без токена его быть не должно."""
    assert (await guarded_client.get("/api/chat")).status == 401
    assert (await guarded_client.post("/api/chat", json={"text": "x"})).status == 401
    assert (await guarded_client.get("/api/chat/stream")).status == 401


# ---------------------------------------------------------------- охрана

async def test_every_api_route_requires_a_token(guarded_client):
    """
    Консоль управляет агентом с доступом к ОС. Незакрытый маршрут — это дыра,
    и заметить её глазами при добавлении нового обработчика легко не получится.
    """
    from src.web.server import make_app

    checked = 0
    for route in make_app().router.routes():
        path = route.resource.canonical
        if not path.startswith("/api/"):
            continue
        checked += 1
        resp = await guarded_client.request(route.method, path)
        assert resp.status == 401, "%s %s открыт без токена" % (route.method, path)

    assert checked >= 15, "маршруты перестали находиться: проверено %d" % checked


async def test_static_files_are_served(client):
    """Страница и её файлы должны отдаваться, иначе консоль просто не откроется."""
    for path, needle in (("/", b"<title>"),
                         ("/console.js", b"apiUrl"),
                         ("/styles.css", b".pulse")):
        resp = await client.get(path)
        assert resp.status == 200, "не отдаётся: %s" % path
        assert needle in await resp.read(), "подменилось содержимое: %s" % path


async def test_unknown_route_is_not_a_crash(client):
    assert (await client.get("/api/выдумка")).status == 404

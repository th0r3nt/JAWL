# -*- coding: utf-8 -*-
"""
Три базы агента: счётчики и очистка.

Читать и чистить приходится по-разному, потому что хранилища ведут себя
по-разному, пока агент работает:

* **реляционная** — обычный SQLite, открывается только для чтения без помех;
* **векторная** — Qdrant в локальном режиме держит `.lock` на каталоге, и его
  клиентом воспользоваться нельзя. Но каждая коллекция лежит в собственном
  `storage.sqlite`, который читается напрямую в режиме «только чтение». Так
  счётчики видны и на работающем агенте — CLI фреймворка в этом случае молча
  показывает нули (`except Exception: pass` в `_get_vector_stats`);
* **граф** — Kuzu берёт исключительную блокировку файла. Второй процесс не может
  ни открыть его, ни даже скопировать. Пока агент жив, счётчик недоступен, и мы
  так и говорим, а не подставляем ноль.

Очистка возможна только на остановленном агенте — это правило самого
фреймворка (`database_manager_screen`: «Cannot manage databases while the agent
is running»), а для векторной и графовой баз ещё и физическое ограничение.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.web import agent
from src.web import config_io as cio

LOCAL_DATA = cio.ROOT_DIR / "src" / "utils" / "local" / "data"

SQL_DB_FILE = LOCAL_DATA / "sql" / "db" / "agent.db"
VECTOR_DB_DIR = LOCAL_DATA / "vector" / "db"
EMBEDDINGS_DIR = LOCAL_DATA / "vector" / "embeddings"
GRAPH_DB_DIR = LOCAL_DATA / "graph"
GRAPH_DB_FILE = GRAPH_DB_DIR / "agent_graph.db"
INTERFACES_DIR = LOCAL_DATA / "interfaces"
SANDBOX_DIR = cio.ROOT_DIR / "sandbox"

BUSY_TIMEOUT_SEC = 5.0

# Таблицы, которые показывает вкладка. Ключ — что стоит в `data-scope`,
# значение — таблица в базе, лимит в settings.yaml и подпись для сообщений.
SQL_MODULES: Dict[str, Tuple[str, Optional[str], str]] = {
    "mental_states": ("mental_states",
                      "system.db.sql.mental_states.max_entities",
                      "состояния сущностей"),
    "tasks": ("tasks", "system.db.sql.tasks.max_tasks", "задачи"),
    "notes": ("notes", "system.db.sql.notes.max_notes", "заметки"),
    "personality_traits": ("personality_traits",
                           "system.db.sql.personality_traits.max_traits",
                           "черты характера"),
    "drives": ("drives", "system.db.sql.drives.max_custom_drives", "мотиваторы"),
}

VECTOR_COLLECTIONS = ("knowledge", "thoughts", "code_ast")

# из src/l1_databases/graph/schema.py
GRAPH_NODE_TABLE = "Concept"
CODE_NODE_TABLE = "CodeNode"

DIR_SIZE_TTL_SEC = 20.0      # профиль браузера может разрастись — не ходим по нему на каждый опрос
DIR_WALK_LIMIT = 20000       # и не считаем бесконечно

# Только что остановленный агент отпускает файлы не мгновенно, а Windows не даёт
# удалить занятый файл вовсе. Пара коротких попыток закрывает этот промежуток.
UNLOCK_ATTEMPTS = 5
UNLOCK_PAUSE_SEC = 0.4


# ---------------------------------------------------------------- вспомогательное

@contextmanager
def _read_only(path: Path):
    """
    Подключение только для чтения: базу держит открытой работающий агент.

    Именно контекстный менеджер, а не голое соединение. У `sqlite3.Connection`
    свой `__enter__`, который фиксирует транзакцию, но **не закрывает** файл —
    на этом уже попались: счётчики опрашиваются раз в несколько секунд, и
    Windows потом отказывался удалять каталог с коллекциями, потому что его
    держала сама консоль.
    """
    conn = sqlite3.connect("file:%s?mode=ro" % path.as_posix(), uri=True,
                           timeout=BUSY_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _count(conn: sqlite3.Connection, table: str) -> Optional[int]:
    try:
        return int(conn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0])
    except sqlite3.Error:
        return None                      # таблицы ещё нет — агент её не создавал


def _settings() -> Dict[str, Any]:
    try:
        return cio.load_yaml(cio.SETTINGS_FILE)
    except Exception:                                    # noqa: BLE001
        return {}


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _tree_size(root: Path) -> Tuple[int, int]:
    """Размер каталога и число файлов; обход ограничен, чтобы не подвешивать опрос."""
    total = files = 0
    if not root.exists():
        return 0, 0
    for path in root.rglob("*"):
        if files >= DIR_WALK_LIMIT:
            break
        try:
            if path.is_file():
                files += 1
                total += path.stat().st_size
        except OSError:
            continue                     # файл занят или исчез между обходами
    return total, files


_dir_cache: Dict[str, Tuple[float, int, int]] = {}


def _cached_tree_size(key: str, root: Path) -> Tuple[int, int]:
    now = time.time()
    cached = _dir_cache.get(key)
    if cached and now - cached[0] < DIR_SIZE_TTL_SEC:
        return cached[1], cached[2]
    total, files = _tree_size(root)
    _dir_cache[key] = (now, total, files)
    return total, files


# ---------------------------------------------------------------- счётчики

def _sql_stats() -> Dict[str, Any]:
    if not SQL_DB_FILE.exists():
        return {"exists": False, "counts": {}, "limits": {}, "sizeBytes": 0}

    settings = _settings()
    counts: Dict[str, Optional[int]] = {}
    limits: Dict[str, Optional[int]] = {}
    drives = {"fundamental": 0, "custom": 0}
    ticks = None

    try:
        with _read_only(SQL_DB_FILE) as conn:
            for key, (table, limit_path, _label) in SQL_MODULES.items():
                counts[key] = _count(conn, table)
                limits[key] = (cio.get_path(settings, limit_path)
                               if limit_path else None)
            ticks = _count(conn, "ticks")
            try:
                for row in conn.execute("SELECT type, COUNT(*) FROM drives GROUP BY type"):
                    if row[0] in drives:
                        drives[row[0]] = int(row[1])
            except sqlite3.Error:
                pass
    except sqlite3.Error as exc:
        return {"exists": True, "error": "база недоступна: %s" % exc,
                "counts": {}, "limits": {}, "sizeBytes": _file_size(SQL_DB_FILE)}

    return {
        "exists": True,
        "counts": counts,
        "limits": limits,
        "drives": drives,
        "ticks": ticks,
        "sizeBytes": _file_size(SQL_DB_FILE),
    }


def _vector_stats() -> Dict[str, Any]:
    """
    Счётчики коллекций Qdrant в обход клиента.

    Локальный Qdrant держит `.lock` на каталоге, поэтому пока агент работает,
    подключиться нельзя. Но точки лежат в обычном SQLite внутри каждой
    коллекции — его читаем напрямую, и цифры честные при живом агенте.
    """
    if not VECTOR_DB_DIR.exists():
        return {"exists": False, "counts": {}, "sizeBytes": 0}

    counts: Dict[str, Optional[int]] = {}
    total = 0
    for name in VECTOR_COLLECTIONS:
        storage = VECTOR_DB_DIR / "collection" / name / "storage.sqlite"
        if not storage.exists():
            counts[name] = None
            continue
        total += _file_size(storage)
        try:
            with _read_only(storage) as conn:
                counts[name] = _count(conn, "points")
        except sqlite3.Error:
            counts[name] = None

    return {"exists": True, "counts": counts, "sizeBytes": total}


def _model_repos() -> Dict[str, str]:
    """
    Соответствие «имя модели в настройках» → «каталог в кэше».

    fastembed скачивает не ту модель, что записана в конфиге, а свою
    ONNX-сборку: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
    лежит на диске как `models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`.
    Список соответствий спрашиваем у самого fastembed, чтобы не хранить его
    копию, которая устареет.
    """
    try:
        from fastembed import TextEmbedding
    except ImportError:
        return {}

    mapping: Dict[str, str] = {}
    try:
        for item in TextEmbedding.list_supported_models():
            name = item.get("model")
            repo = (item.get("sources") or {}).get("hf")
            if name and repo:
                mapping[name] = "models--" + repo.replace("/", "--")
    except Exception:                                    # noqa: BLE001
        return {}
    return mapping


def _embedding_stats() -> Dict[str, Any]:
    """
    Скачанные модели эмбеддингов.

    Веса весят сотни мегабайт и остаются на диске после смены модели в
    настройках — сами они не удаляются. Помечаем, какая из них используется
    сейчас, чтобы было видно, что можно убрать.
    """
    if not EMBEDDINGS_DIR.exists():
        return {"exists": False, "models": [], "sizeBytes": 0}

    settings = _settings()
    active_name = cio.get_path(settings, "system.db.vector.embedding_model") or ""
    active_dir = _model_repos().get(active_name, "")
    by_dir = {folder: name for name, folder in _model_repos().items()}

    models: List[Dict[str, Any]] = []
    total = 0
    for path in sorted(EMBEDDINGS_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue                     # .locks — служебный каталог huggingface
        size, files = _cached_tree_size("emb:" + path.name, path)
        total += size
        models.append({
            "dir": path.name,
            # если fastembed не знает каталог, показываем как есть
            "title": by_dir.get(path.name, path.name.replace("models--", "").replace("--", "/")),
            "active": path.name == active_dir,
            "sizeBytes": size,
            "files": files,
        })

    return {
        "exists": True,
        "models": models,
        "sizeBytes": total,
        "activeModel": active_name,
        # настройка есть, а весов под неё нет — модель скачается при запуске
        "activeDownloaded": any(m["active"] for m in models),
    }


def _graph_stats(agent_running: bool) -> Dict[str, Any]:
    """
    Счётчик вершин графа.

    Kuzu берёт исключительную блокировку файла: пока агент работает, открыть
    базу невозможно даже на чтение. Возвращаем `locked`, чтобы интерфейс сказал
    об этом прямо, а не показал ноль.
    """
    if not GRAPH_DB_FILE.exists():
        return {"exists": False, "locked": False, "counts": {}, "sizeBytes": 0}

    size = _file_size(GRAPH_DB_FILE)
    if agent_running:
        return {"exists": True, "locked": True, "counts": {}, "sizeBytes": size}

    try:
        import kuzu
    except ImportError:
        return {"exists": True, "locked": False, "counts": {},
                "error": "kuzu не установлен", "sizeBytes": size}

    try:
        db = kuzu.Database(str(GRAPH_DB_FILE), read_only=True)
        conn = kuzu.Connection(db)
        counts = {
            "concepts": _kuzu_count(conn, GRAPH_NODE_TABLE),
            "code": _kuzu_count(conn, CODE_NODE_TABLE),
        }
        conn.close()
        db.close()
    except Exception as exc:                             # noqa: BLE001
        # база может быть занята и без нашего агента — например, открытым CLI
        return {"exists": True, "locked": True, "counts": {},
                "error": str(exc)[:160], "sizeBytes": size}

    return {"exists": True, "locked": False, "counts": counts, "sizeBytes": size}


def _kuzu_count(conn: Any, table: str) -> Optional[int]:
    try:
        result = conn.execute("MATCH (n:%s) RETURN count(n)" % table)
        return int(result.get_next()[0]) if result.has_next() else 0
    except Exception:                                    # noqa: BLE001
        return None                      # таблицы может не быть, если граф кода выключен


def stats() -> Dict[str, Any]:
    """Всё, что показывает вкладка «База данных»."""
    running = bool(agent.status().get("running"))

    cache_size, cache_files = _cached_tree_size("interfaces", INTERFACES_DIR)
    sandbox_size, sandbox_files = _cached_tree_size("sandbox", SANDBOX_DIR)

    return {
        "ok": True,
        "agentRunning": running,
        "sql": _sql_stats(),
        "vector": _vector_stats(),
        "embeddings": _embedding_stats(),
        "graph": _graph_stats(running),
        "dirs": {
            "interfaces": {"sizeBytes": cache_size, "files": cache_files,
                           "exists": INTERFACES_DIR.exists()},
            "sandbox": {"sizeBytes": sandbox_size, "files": sandbox_files,
                        "exists": SANDBOX_DIR.exists()},
        },
    }


# ---------------------------------------------------------------- очистка

EMBEDDING_PREFIX = "embeddings."


def known_scope(scope: str) -> bool:
    """
    Известна ли область.

    Модели эмбеддингов появляются и исчезают, поэтому их имена не перечислить
    заранее: проверяем, что такой каталог действительно лежит в кэше. Заодно это
    отсекает попытку выйти за его пределы.
    """
    if scope in SCOPE_LABELS:
        return True
    if not scope.startswith(EMBEDDING_PREFIX):
        return False
    return _embedding_dir(scope) is not None


def _embedding_dir(scope: str) -> Optional[Path]:
    """Каталог модели по имени области — или None, если такого нет."""
    name = scope[len(EMBEDDING_PREFIX):]
    if not name or name.startswith(".") or "/" in name or "\\" in name:
        return None

    target = (EMBEDDINGS_DIR / name).resolve()
    try:
        target.relative_to(EMBEDDINGS_DIR.resolve())
    except ValueError:
        return None                      # путь увёл за пределы кэша
    return target if target.is_dir() else None


def scope_label(scope: str) -> str:
    """Человеческое имя области — для подтверждений и сообщений."""
    if scope in SCOPE_LABELS:
        return SCOPE_LABELS[scope]
    if scope.startswith(EMBEDDING_PREFIX):
        return "модель эмбеддингов " + scope[len(EMBEDDING_PREFIX):]
    return scope


SCOPE_LABELS: Dict[str, str] = {
    "sql.all": "реляционную базу",
    "vector.all": "векторную базу",
    "vector.knowledge": "коллекцию knowledge",
    "vector.thoughts": "коллекцию thoughts",
    "vector.code_ast": "коллекцию code_ast",
    "graph.concepts": "понятия в графе",
    "graph.all": "граф знаний",
    "interfaces.all": "кэш интерфейсов и песочницу",
    "embeddings.all": "все скачанные модели эмбеддингов",
}
SCOPE_LABELS.update({"sql.%s" % key: label
                     for key, (_t, _l, label) in SQL_MODULES.items()})


def _clear_sandbox() -> None:
    """
    Повторяет `_clear_sandbox` из `src/cli/screens/database_manager.py`.

    Содержимое каталога удаляется, но служебная структура восстанавливается —
    иначе агент не найдёт папку загрузок и шину событий. Логика продублирована,
    а не импортирована: модуль CLI тянет за собой questionary и весь интерфейс
    командной строки. Совпадение состава проверяется тестом.
    """
    if SANDBOX_DIR.exists():
        for item in SANDBOX_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except OSError:
                continue

    system_dir = SANDBOX_DIR / "_system"
    (system_dir / "download").mkdir(parents=True, exist_ok=True)
    (system_dir / ".jawl_events").mkdir(parents=True, exist_ok=True)

    template = cio.ROOT_DIR / "src" / "utils" / "templates" / "framework_api.py"
    if template.exists():
        shutil.copy2(template, system_dir / "framework_api.py")


def _remove(path: Path) -> None:
    """
    Удаляет файл или каталог, переживая ещё не отпущенную блокировку.

    Windows не даёт удалить занятый файл: `PermissionError [WinError 32]`. Такое
    бывает в первые доли секунды после остановки агента, пока закрываются его
    соединения. Пробуем несколько раз, и только потом сдаёмся.
    """
    last: Optional[OSError] = None
    for attempt in range(UNLOCK_ATTEMPTS):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            return
        except OSError as exc:
            last = exc
            if attempt + 1 < UNLOCK_ATTEMPTS:
                time.sleep(UNLOCK_PAUSE_SEC)

    raise BusyError(
        "не удалось удалить «%s»: файл занят другим процессом. "
        "Обычно это ещё не закрывшийся агент — подождите секунду и повторите. "
        "Если не помогает, проверьте, не открыт ли каталог в проводнике "
        "или в другой консоли JAWL." % path.name
    ) from last


class BusyError(RuntimeError):
    """Файл занят и после нескольких попыток."""


def _wipe_sql_table(table: str) -> str:
    if not SQL_DB_FILE.exists():
        return "база и так пуста"
    conn = sqlite3.connect(str(SQL_DB_FILE), timeout=BUSY_TIMEOUT_SEC)
    try:
        removed = conn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
        conn.execute('DELETE FROM "%s"' % table)
        conn.commit()
    finally:
        conn.close()
    return "удалено записей: %d" % removed


def _wipe_vector_collection(name: str) -> str:
    """
    Чистит коллекцию, не удаляя её саму.

    CLI на этом месте пересоздаёт коллекцию, подставляя `vector_size` из
    settings.yaml. Это опасно: если размерность в конфиге успели поменять (а
    поле редактируется на вкладке «Память»), пересозданная коллекция получит
    размерность, несовместимую с уже накопленными эмбеддингами и с соседними
    коллекциями. Удаление точек не выводит схему заново и такого рассогласования
    не создаёт.
    """
    from qdrant_client import QdrantClient, models

    client = QdrantClient(path=str(VECTOR_DB_DIR))
    try:
        before = client.count(name).count
        client.delete(collection_name=name,
                      points_selector=models.FilterSelector(filter=models.Filter()))
    finally:
        client.close()
    return "удалено записей: %d" % before


def _wipe_graph_concepts() -> str:
    import kuzu

    db = kuzu.Database(str(GRAPH_DB_FILE))
    conn = kuzu.Connection(db)
    try:
        before = _kuzu_count(conn, GRAPH_NODE_TABLE) or 0
        # DETACH DELETE снимает и связи: иначе Kuzu не даст удалить вершину
        conn.execute("MATCH (n:%s) DETACH DELETE n" % GRAPH_NODE_TABLE)
    finally:
        conn.close()
        db.close()
    return "удалено понятий: %d" % before


def wipe(scope: str) -> Dict[str, Any]:
    """
    Необратимо стирает выбранную область.

    Работает только на остановленном агенте. Это правило самого фреймворка, и
    для двух из трёх баз ещё и физика: Qdrant держит `.lock` на каталоге, Kuzu —
    исключительную блокировку файла. А правка SQLite под работающим агентом
    разошлась бы с его состоянием в памяти.
    """
    if not known_scope(scope):
        return {"ok": False, "error": "неизвестная область: %s" % scope}

    if agent.status().get("running"):
        return {
            "ok": False,
            "needsStop": True,
            "error": "Агент запущен. Базы он держит открытыми, "
                     "и очистка разошлась бы с его состоянием в памяти. "
                     "Остановите агента и повторите.",
        }

    try:
        detail = _perform(scope)
    except BusyError as exc:
        return {"ok": False, "busy": True, "error": str(exc)}
    except Exception as exc:                             # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:200])}

    _dir_cache.clear()
    return {"ok": True, "scope": scope, "label": scope_label(scope), "detail": detail}


def _perform(scope: str) -> str:
    kind, _, name = scope.partition(".")

    if kind == "embeddings":
        if name == "all":
            if not EMBEDDINGS_DIR.exists():
                return "кэш и так пуст"
            _remove(EMBEDDINGS_DIR)
            return "веса удалены, модель скачается при следующем запуске"
        folder = _embedding_dir(scope)
        if folder is None:
            return "модель уже удалена"
        _remove(folder)
        _dir_cache.pop("emb:" + name, None)
        return "веса удалены, при необходимости модель скачается заново"

    if kind == "sql":
        if name == "all":
            if not SQL_DB_FILE.exists():
                return "база и так пуста"
            _remove(SQL_DB_FILE)
            return "файл базы удалён, агент создаст её заново"
        return _wipe_sql_table(SQL_MODULES[name][0])

    if kind == "vector":
        if not VECTOR_DB_DIR.exists():
            return "база и так пуста"
        if name == "all":
            _remove(VECTOR_DB_DIR)
            return "каталог удалён, коллекции создадутся заново"
        return _wipe_vector_collection(name)

    if kind == "graph":
        if not GRAPH_DB_FILE.exists():
            return "граф и так пуст"
        if name == "all":
            _remove(GRAPH_DB_DIR)
            return "файл графа удалён, агент создаст его заново"
        return _wipe_graph_concepts()

    if kind == "interfaces":
        if INTERFACES_DIR.exists():
            _remove(INTERFACES_DIR)
        _clear_sandbox()
        return "кэш удалён, песочница очищена и восстановлена"

    return "нечего делать"


def scopes() -> List[str]:
    return sorted(SCOPE_LABELS)

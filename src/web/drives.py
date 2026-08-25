# -*- coding: utf-8 -*-
"""
Мотиваторы: живое состояние из базы агента.

Дефицит нигде не хранится — он вычисляется из времени последнего насыщения.
Формула повторяет `_calculate_deficit` из
`src/l1_databases/sql/management/drives/crud.py`; расходиться им нельзя, за этим
следит тест, сверяющий обе реализации на общих данных.

Два вида мотиваторов ведут себя по-разному:

* **фундаментальные** (Curiosity, Social, Mastery) описаны в `settings.yaml`, и
  при каждом старте фреймворк перезаписывает их значения в базе из конфига —
  а выключенные удаляет. Править их надо в конфиге, база тут ведомая;
* **свои** созданы самим агентом и существуют только в базе, в конфиге их нет.

Читаем базу в режиме только для чтения: агент работает и держит её открытой.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.web import config_io as cio

DB_FILE = cio.ROOT_DIR / "src" / "utils" / "local" / "data" / "sql" / "db" / "agent.db"

BUSY_TIMEOUT_SEC = 5.0

# имена в базе английские, в интерфейсе — русские
FUNDAMENTAL_TITLES = {
    "Curiosity": ("curiosity", "Любопытство"),
    "Social": ("social", "Общение"),
    "Mastery": ("mastery", "Мастерство"),
}

# Описания фундаментальных мотиваторов фреймворк держит по-английски
# (`fundamental_defs` в crud.py) и переписывает их в базе при каждом старте.
# Свои мотиваторы агент описывает сам и по-русски, так что рядом с ними
# английский текст выглядел бы чужеродно — переводим, как и названия.
FUNDAMENTAL_DESCRIPTIONS = {
    "curiosity": "Потребность расширять базу знаний: поиск незнакомых понятий, "
                 "разбор внешних источников, пополнение семантической памяти.",
    "social": "Потребность в общении: обработка входящих обращений, присутствие "
              "в каналах связи, инициатива в диалоге.",
    "mastery": "Стремление к порядку и результату: продвижение долгих задач, "
               "структурирование данных, самодиагностика.",
}


def exists() -> bool:
    return DB_FILE.exists()


@contextmanager
def _connect(read_only: bool = True):
    """
    Соединение с базой агента, закрывающееся гарантированно.

    `with sqlite3.connect(...)` закрывает транзакцию, но не файл. Шкалы
    опрашиваются раз в десять секунд, так что утечка дескрипторов накапливалась
    и мешала потом удалить файлы баз.
    """
    if read_only:
        conn = sqlite3.connect("file:%s?mode=ro" % DB_FILE.as_posix(), uri=True,
                               timeout=BUSY_TIMEOUT_SEC)
    else:
        conn = sqlite3.connect(str(DB_FILE), timeout=BUSY_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _parse_time(raw: Any) -> Optional[datetime]:
    """Время хранится наивным, но это UTC."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        moment = raw
    else:
        text = str(raw).replace("T", " ").split("+")[0].strip()
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                moment = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def calculate_deficit(last_satisfied: datetime, now: datetime,
                      decay_rate: float, decay_interval_sec: int,
                      dynamic_reduction: bool) -> float:
    """
    Дефицит в процентах. Копия формулы фреймворка.

    Ключ называется decay, но дефицит именно растёт. При `dynamic_reduction`
    рост замедляется: до 50% полная скорость, 50–80% вдвое медленнее,
    дальше впятеро.
    """
    if decay_rate <= 0 or decay_interval_sec <= 0:
        return 0.0

    intervals = (now - last_satisfied).total_seconds() / max(1, decay_interval_sec)
    if intervals < 0:
        intervals = 0.0

    if not dynamic_reduction:
        return min(100.0, intervals * decay_rate)

    t50 = 50.0 / decay_rate
    t80 = t50 + 30.0 / (decay_rate * 0.5)

    if intervals <= t50:
        deficit = intervals * decay_rate
    elif intervals <= t80:
        deficit = 50.0 + (intervals - t50) * (decay_rate * 0.5)
    else:
        deficit = 80.0 + (intervals - t80) * (decay_rate * 0.2)

    return min(100.0, deficit)


def _dynamic_reduction() -> bool:
    try:
        settings = cio.load_yaml(cio.SETTINGS_FILE)
        value = cio.get_path(settings, "system.db.sql.drives.dynamic_reduction", True)
        return bool(value)
    except Exception:                                  # noqa: BLE001
        return True


def _config_pair(key: str) -> Dict[str, Any]:
    """Что записано в settings.yaml для фундаментального мотиватора."""
    try:
        settings = cio.load_yaml(cio.SETTINGS_FILE)
    except Exception:                                  # noqa: BLE001
        return {}
    root = "system.db.sql.drives.fundamental.%s" % key
    return {
        "rate": cio.get_path(settings, root + ".decay.rate"),
        "interval": cio.get_path(settings, root + ".decay.interval_sec"),
        "enabled": cio.get_path(settings, root + ".enabled"),
    }


def list_drives() -> Dict[str, Any]:
    """Все мотиваторы с вычисленным дефицитом."""
    if not exists():
        return {"ok": True, "drives": [], "missing": True}

    dynamic = _dynamic_reduction()
    now = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []

    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, name, type, description, decay_rate,"
                " decay_interval_sec, last_satisfied_at, recent_reflections"
                " FROM drives"
            ).fetchall()
    except sqlite3.Error as exc:
        return {"ok": False, "error": "база недоступна: %s" % exc}

    for row in rows:
        last = _parse_time(row["last_satisfied_at"])
        rate = float(row["decay_rate"] or 0)
        interval = int(row["decay_interval_sec"] or 0)

        deficit = calculate_deficit(last, now, rate, interval, dynamic) if last else 0.0

        try:
            reflections = json.loads(row["recent_reflections"] or "[]")
        except (TypeError, ValueError):
            reflections = []

        item: Dict[str, Any] = {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "description": row["description"] or "",
            "decayRate": rate,
            "decayIntervalSec": interval,
            "lastSatisfiedAt": last.isoformat() if last else None,
            "deficit": round(deficit, 1),
            "reflections": reflections if isinstance(reflections, list) else [],
        }

        pair = FUNDAMENTAL_TITLES.get(row["name"])
        if pair:
            key, title = pair
            item["key"] = key
            item["title"] = title
            item["description"] = FUNDAMENTAL_DESCRIPTIONS.get(key, item["description"])
            cfg = _config_pair(key)
            item["config"] = cfg
            # конфиг применяется при старте: пока агент работает, база может
            # расходиться с только что сохранёнными значениями
            item["pendingRestart"] = bool(
                cfg and (
                    (cfg.get("rate") is not None and float(cfg["rate"]) != rate)
                    or (cfg.get("interval") is not None and int(cfg["interval"]) != interval)
                )
            )
        else:
            item["title"] = row["name"]
            item["pendingRestart"] = False

        out.append(item)

    order = {"fundamental": 0, "custom": 1}
    out.sort(key=lambda d: (order.get(d["type"], 2), d["title"]))
    return {"ok": True, "drives": out, "dynamicReduction": dynamic}


def update_custom(updates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Правит скорость и интервал у своих мотиваторов.

    Фундаментальные не трогаем: их значения задаются в settings.yaml и
    перезаписываются при каждом старте — правка базы была бы обманом.
    """
    if not updates:
        return {"ok": True, "updated": []}
    if not exists():
        return {"ok": False, "error": "база агента не найдена"}

    updated, skipped = [], []
    try:
        with _connect(read_only=False) as conn:
            for drive_id, values in updates.items():
                row = conn.execute(
                    "SELECT type, name FROM drives WHERE id = ?", (drive_id,)
                ).fetchone()
                if row is None:
                    skipped.append(drive_id)
                    continue
                if row["type"] != "custom":
                    skipped.append(row["name"])
                    continue

                rate = values.get("decayRate")
                interval = values.get("decayIntervalSec")
                if rate is None and interval is None:
                    continue

                rate = float(rate) if rate is not None else None
                interval = int(interval) if interval is not None else None
                if (rate is not None and rate <= 0) or (interval is not None and interval <= 0):
                    # фреймворк на таких значениях отключает мотиватор целиком
                    skipped.append(row["name"])
                    continue

                if rate is not None and interval is not None:
                    conn.execute(
                        "UPDATE drives SET decay_rate = ?, decay_interval_sec = ? WHERE id = ?",
                        (rate, interval, drive_id))
                elif rate is not None:
                    conn.execute("UPDATE drives SET decay_rate = ? WHERE id = ?",
                                 (rate, drive_id))
                else:
                    conn.execute("UPDATE drives SET decay_interval_sec = ? WHERE id = ?",
                                 (interval, drive_id))
                updated.append(drive_id)
            conn.commit()
    except sqlite3.OperationalError as exc:
        return {"ok": False, "error": "база занята агентом: %s" % exc}
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "updated": updated, "skipped": skipped}

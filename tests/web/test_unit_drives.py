# -*- coding: utf-8 -*-
"""
Мотиваторы: расчёт дефицита и правка своих.

Самое важное здесь — что формула дефицита совпадает с той, по которой живёт
сам агент. Разойдутся — консоль будет рисовать шкалу, не имеющую отношения к
реальному поведению.
"""

import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.web import drives

NOW = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """Копия схемы таблицы drives во временной базе."""
    path = tmp_path / "agent.db"
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE drives (
            id TEXT PRIMARY KEY, name TEXT, type TEXT, description TEXT,
            decay_rate REAL, decay_interval_sec INTEGER,
            last_satisfied_at TEXT, recent_reflections TEXT
        )""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(drives, "DB_FILE", path)
    return path


def add(path, drive_id, name, kind, rate, interval, ago_sec, reflections=None):
    last = datetime.now(timezone.utc) - timedelta(seconds=ago_sec)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO drives VALUES (?,?,?,?,?,?,?,?)",
                 (drive_id, name, kind, "описание", rate, interval,
                  last.strftime("%Y-%m-%d %H:%M:%S.%f"),
                  json.dumps(reflections or [])))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- формула

@pytest.mark.parametrize("dynamic", [True, False])
def test_formula_matches_the_framework(dynamic):
    """
    Сверка с `_calculate_deficit` из
    src/l1_databases/sql/management/drives/crud.py на случайных наборах.
    Этот тест и есть страховка от расхождения.
    """
    from src.l1_databases.sql.management.drives.crud import SQLDrives

    reference = SQLDrives(db=None, dynamic_reduction=dynamic)
    random.seed(20260825)

    for _ in range(500):
        rate = round(random.uniform(0.5, 40.0), 2)
        interval = random.randint(60, 86400)
        last = NOW - timedelta(seconds=random.uniform(0, 400000))

        theirs = reference._calculate_deficit(last, NOW, rate, interval)
        ours = drives.calculate_deficit(last, NOW, rate, interval, dynamic)
        assert abs(theirs - ours) < 1e-9, (rate, interval, last)


def test_deficit_never_exceeds_hundred():
    ancient = NOW - timedelta(days=3650)
    assert drives.calculate_deficit(ancient, NOW, 12.0, 1200, True) == 100.0
    assert drives.calculate_deficit(ancient, NOW, 12.0, 1200, False) == 100.0


def test_dynamic_reduction_slows_growth_after_half():
    """До 50% скорость полная, дальше — медленнее. Иначе смысл флага теряется."""
    rate, interval = 10.0, 600
    t50 = 50.0 / rate * interval

    at_half = drives.calculate_deficit(NOW - timedelta(seconds=t50), NOW, rate, interval, True)
    assert abs(at_half - 50.0) < 1e-6

    later = NOW - timedelta(seconds=t50 * 2)
    slowed = drives.calculate_deficit(later, NOW, rate, interval, True)
    linear = drives.calculate_deficit(later, NOW, rate, interval, False)
    assert slowed < linear, "нелинейное накопление не замедлило рост"


def test_broken_settings_give_zero_not_a_crash():
    """Фреймворк на нулевых значениях отключает мотиватор; делить на ноль нельзя."""
    assert drives.calculate_deficit(NOW, NOW, 0.0, 1200, True) == 0.0
    assert drives.calculate_deficit(NOW, NOW, 12.0, 0, True) == 0.0


# ---------------------------------------------------------------- чтение

def test_missing_database_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(drives, "DB_FILE", tmp_path / "нет.db")
    res = drives.list_drives()
    assert res["ok"] is True and res["missing"] is True and res["drives"] == []


def test_reads_rows_and_computes_deficit(agent_db, monkeypatch):
    monkeypatch.setattr(drives, "_dynamic_reduction", lambda: False)
    add(agent_db, "a1", "Curiosity", "fundamental", 12.0, 1200, ago_sec=1200)

    res = drives.list_drives()
    drive = res["drives"][0]

    assert drive["title"] == "Любопытство", "имя из базы не переведено"
    assert drive["key"] == "curiosity"
    assert abs(drive["deficit"] - 12.0) < 0.5, drive["deficit"]


def test_custom_drive_keeps_its_own_name(agent_db, monkeypatch):
    """Свой мотиватор в словаре переводов не значится — показываем как есть."""
    monkeypatch.setattr(drives, "_dynamic_reduction", lambda: False)
    add(agent_db, "c1", "UserCare", "custom", 10.0, 900, ago_sec=450)

    drive = drives.list_drives()["drives"][0]
    assert drive["title"] == "UserCare"
    assert drive["type"] == "custom"
    assert "key" not in drive


def test_fundamentals_come_before_custom(agent_db, monkeypatch):
    monkeypatch.setattr(drives, "_dynamic_reduction", lambda: False)
    add(agent_db, "c1", "UserCare", "custom", 10.0, 900, ago_sec=100)
    add(agent_db, "a1", "Mastery", "fundamental", 8.0, 1200, ago_sec=100)

    kinds = [d["type"] for d in drives.list_drives()["drives"]]
    assert kinds == ["fundamental", "custom"]


def test_divergence_with_config_is_reported(agent_db, monkeypatch):
    """
    Фреймворк переписывает значения фундаментальных из settings.yaml при
    каждом старте. Пока агент работает, база может отставать — об этом надо
    сказать, а не показывать одно вместо другого.
    """
    monkeypatch.setattr(drives, "_dynamic_reduction", lambda: False)
    monkeypatch.setattr(drives, "_config_pair",
                        lambda key: {"rate": 25.0, "interval": 600, "enabled": True})
    add(agent_db, "a1", "Social", "fundamental", 18.0, 900, ago_sec=100)

    drive = drives.list_drives()["drives"][0]
    assert drive["pendingRestart"] is True
    assert drive["decayRate"] == 18.0, "показано значение из конфига вместо базы"


def test_no_divergence_when_values_match(agent_db, monkeypatch):
    monkeypatch.setattr(drives, "_dynamic_reduction", lambda: False)
    monkeypatch.setattr(drives, "_config_pair",
                        lambda key: {"rate": 18.0, "interval": 900, "enabled": True})
    add(agent_db, "a1", "Social", "fundamental", 18.0, 900, ago_sec=100)

    assert drives.list_drives()["drives"][0]["pendingRestart"] is False


def test_broken_reflections_do_not_break_reading(agent_db, monkeypatch):
    monkeypatch.setattr(drives, "_dynamic_reduction", lambda: False)
    add(agent_db, "a1", "Curiosity", "fundamental", 12.0, 1200, ago_sec=100)
    conn = sqlite3.connect(agent_db)
    conn.execute("UPDATE drives SET recent_reflections = 'не json'")
    conn.commit()
    conn.close()

    assert drives.list_drives()["drives"][0]["reflections"] == []


# ---------------------------------------------------------------- запись

def test_updates_custom_drive(agent_db):
    add(agent_db, "c1", "UserCare", "custom", 10.0, 900, ago_sec=100)

    res = drives.update_custom({"c1": {"decayRate": 14.5, "decayIntervalSec": 1500}})
    assert res["ok"] is True and res["updated"] == ["c1"]

    row = sqlite3.connect(agent_db).execute(
        "SELECT decay_rate, decay_interval_sec FROM drives WHERE id='c1'").fetchone()
    assert row == (14.5, 1500)


def test_refuses_to_touch_fundamental(agent_db):
    """
    Значения фундаментальных задаёт settings.yaml и перезаписывает при старте.
    Правка базы выглядела бы применённой, а через перезапуск исчезла.
    """
    add(agent_db, "a1", "Curiosity", "fundamental", 12.0, 1200, ago_sec=100)

    res = drives.update_custom({"a1": {"decayRate": 99.0}})
    assert res["ok"] is True
    assert res["updated"] == [] and "Curiosity" in res["skipped"]

    row = sqlite3.connect(agent_db).execute(
        "SELECT decay_rate FROM drives WHERE id='a1'").fetchone()
    assert row[0] == 12.0, "значение фундаментального изменено"


@pytest.mark.parametrize("bad", [{"decayRate": 0}, {"decayRate": -5},
                                 {"decayIntervalSec": 0}, {"decayIntervalSec": -60}])
def test_rejects_non_positive_values(agent_db, bad):
    """На нулях и минусах фреймворк отключает мотиватор с предупреждением."""
    add(agent_db, "c1", "UserCare", "custom", 10.0, 900, ago_sec=100)

    res = drives.update_custom({"c1": bad})
    assert res["updated"] == []

    row = sqlite3.connect(agent_db).execute(
        "SELECT decay_rate, decay_interval_sec FROM drives WHERE id='c1'").fetchone()
    assert row == (10.0, 900)


def test_unknown_id_is_skipped(agent_db):
    res = drives.update_custom({"нет-такого": {"decayRate": 5}})
    assert res["ok"] is True and res["updated"] == []


def test_empty_update_touches_nothing(agent_db):
    assert drives.update_custom({}) == {"ok": True, "updated": []}

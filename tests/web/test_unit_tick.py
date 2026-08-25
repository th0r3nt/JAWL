# -*- coding: utf-8 -*-
"""
Состояние такта, восстановленное из журнала.

Здесь два разных риска, и оба проверяются отдельно:

* мы неверно повторяем расчёт пробуждения из `heartbeat.py` — тогда шапка
  показывает неправильный обратный отсчёт;
* фреймворк поменял формулировки в журнале — тогда мы вообще ничего не
  распознаём, и шапка молча замирает. Этот риск ловит `test_markers_*`,
  сверяющий шаблоны с исходником фреймворка.
"""

import re
from datetime import datetime, timedelta

import pytest

from src.web import logs, tick

BASE = datetime(2026, 8, 25, 12, 0, 0)
INTERVAL = 600


def line(offset_sec, message, level="INFO", logger="JAWL.Agent"):
    stamp = (BASE + timedelta(seconds=offset_sec)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return "%s - %s - %s - %s\n" % (stamp, logger, level, message)


@pytest.fixture
def watcher(tmp_path, monkeypatch):
    """
    Разбор поверх временного журнала с фиксированным интервалом такта.

    Настоящий `logs/main.log` не трогаем: он принадлежит работающему агенту.
    """
    log_file = tmp_path / "main.log"
    log_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(logs, "LOG_FILE", log_file)

    watch = tick.TickWatcher()
    monkeypatch.setattr(watch, "_config", lambda: (INTERVAL, False, 8))

    def append(*rows):
        with open(log_file, "a", encoding="utf-8", newline="") as fh:
            fh.write("".join(rows))
        return watch.poll()

    watch.append = append
    watch.log_file = log_file
    return watch


def at(now_offset, monkeypatch):
    """Подменяет «сейчас» внутри модуля: без этого отсчёт зависит от часов."""
    moment = BASE + timedelta(seconds=now_offset)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    monkeypatch.setattr(tick, "datetime", Frozen)


# ---------------------------------------------------------------- обратный отсчёт

def test_countdown_starts_from_the_end_of_the_cycle(watcher, monkeypatch):
    """
    Фреймворк назначает следующий такт от конца цикла, а не от начала:
    `_next_tick_time = time.time() + heartbeat_interval` после await задачи.
    """
    at(120, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, "[ReAct] Step 1/8."),
        line(60, "[ReAct] Empty actions list received. Concluding cycle."),
    )

    assert state["phase"] == "sleep"
    # цикл кончился на 60-й секунде, «сейчас» 120-я: 600 - 60 = 540
    assert state["wakeInSec"] == pytest.approx(540, abs=1)


def test_accelerating_event_is_the_authoritative_anchor(watcher, monkeypatch):
    """
    При событии-ускорителе журнал печатает уже посчитанный остаток. Своей
    арифметике тут доверять нельзя — множители зависят от глубины сна.
    """
    at(80, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Empty actions list received. Concluding cycle."),
        line(50, "[Heartbeat] Incoming event: 'OS_FILE_MODIFIED' (LOW). "
                 "Next LLM execution scheduled sooner by 154.7 sec. Until wakeup: 361.0 sec."),
    )

    # 50 + 361 = 411-я секунда, «сейчас» 80-я
    assert state["wakeInSec"] == pytest.approx(331, abs=1)


def test_custom_sleep_sets_its_own_deadline(watcher, monkeypatch):
    at(100, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Empty actions list received. Concluding cycle."),
        line(10, "[Heartbeat] Custom sleep mode engaged for 01:00:00 (depth: 'deep')."),
    )

    assert state["sleepDepth"] == "deep"
    assert state["wakeInSec"] == pytest.approx(3600 - 90, abs=1)


def test_cycle_after_custom_sleep_does_not_rearm_the_interval(watcher, monkeypatch):
    """
    Тонкость `heartbeat.py`: признак своего сна снимается на входе в цикл, и
    тогда по завершении `_next_tick_time` не пересчитывается. Следующий такт
    начинается сразу, а не через интервал.
    """
    at(4000, monkeypatch)
    state = watcher.append(
        line(0, "[Heartbeat] Custom sleep mode engaged for 01:00:00 (depth: 'deep')."),
        line(3600, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(3650, "[ReAct] Empty actions list received. Concluding cycle."),
    )

    assert state["sleepDepth"] == "normal", "глубина сна должна сброситься"
    assert state["wakeInSec"] == 0, "интервал не должен применяться после своего сна"


def test_interrupted_cycle_wakes_immediately(watcher, monkeypatch):
    at(70, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(30, "[Heartbeat] Interrupted current ReAct cycle due to event: "
                 "AIOGRAM_MESSAGE_INCOMING (CRITICAL)", level="WARNING"),
        line(31, "[System] Current ReAct cycle successfully cancelled.", logger="JAWL"),
    )

    assert state["phase"] == "sleep"
    assert state["wakeInSec"] == 0


def test_continuous_cycle_never_waits(watcher, monkeypatch):
    watcher._config = lambda: (INTERVAL, True, 8)
    at(120, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Empty actions list received. Concluding cycle."))

    assert state["continuous"] is True
    assert state["wakeInSec"] == 0


# ---------------------------------------------------------------- фазы и шаги

def test_cycle_start_switches_to_wake(watcher, monkeypatch):
    at(5, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. "
                "Reason: AIOGRAM_MESSAGE_INCOMING (LLM Model: google/gemini-3.7-flash)."))

    assert state["phase"] == "wake"
    assert state["reason"] == "AIOGRAM_MESSAGE_INCOMING"
    assert state["model"] == "google/gemini-3.7-flash"
    assert state["wakeInSec"] is None, "во время цикла обратный отсчёт бессмыслен"


def test_step_is_counted_once_despite_two_loggers(watcher, monkeypatch):
    """Строку шага пишут и JAWL, и JAWL.Agent — всплеск должен быть один."""
    at(5, monkeypatch)
    watcher.poll()                       # восстановление по пустому журналу
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, "[ReAct] Step 3/8.", logger="JAWL"),
        line(1, "[ReAct] Step 3/8.", logger="JAWL.Agent"),
    )

    assert (state["step"], state["maxSteps"]) == (3, 8)
    assert len([e for e in state["events"] if e["kind"] == "step"]) == 1


def test_shutdown_turns_the_header_off(watcher, monkeypatch):
    at(30, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(10, "[Heartbeat] Orchestrator stopped."),
    )

    assert state["phase"] == "off"
    assert state["step"] == 0


def test_startup_arms_the_first_tick(watcher, monkeypatch):
    at(60, monkeypatch)
    state = watcher.append(line(0, "[System] JAWL started successfully", logger="JAWL"))

    assert state["phase"] == "sleep"
    assert state["wakeInSec"] == pytest.approx(540, abs=1)


def test_unknown_state_until_the_log_says_something(watcher, monkeypatch):
    at(1, monkeypatch)
    state = watcher.append(line(0, "[Vector DB] Database initialized at ./data"))

    assert state["known"] is False and state["phase"] == "unknown"


# ------------------------------------------------- цикл, исчерпавший лимит шагов

def test_exhausted_cycle_waits_for_the_model_before_settling(watcher, monkeypatch):
    """
    Выход по лимиту шагов фреймворк не логирует. Пока модель не ответила,
    тишина в журнале — это ожидание ответа, а не конец такта.
    """
    at(100, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, "[ReAct] Step 8/8."),
        line(2, "[LLM] Input tokens: 14476."),
    )

    assert state["phase"] == "wake", "молчание во время запроса к модели — не сон"


def test_exhausted_cycle_settles_after_quiet(watcher, monkeypatch):
    at(100, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, "[ReAct] Step 8/8."),
        line(2, "[LLM] Input tokens: 14476."),
        line(20, "[LLM] Output tokens: 247."),
        line(21, "[Vector-Graph RAG] Extracted: 10 vector anchors, 2 graph nodes."),
    )

    assert state["phase"] == "sleep"
    # такт отсчитывается от последней строки цикла, а не от «сейчас»
    assert state["wakeInSec"] == pytest.approx(600 - (100 - 21), abs=1)


def test_exhausted_cycle_is_not_settled_too_early(watcher, monkeypatch):
    at(25, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, "[ReAct] Step 8/8."),
        line(20, "[LLM] Output tokens: 247."),
    )

    assert state["phase"] == "wake", "5 секунд тишины — ещё не конец цикла"


# ---------------------------------------------------------------- чем занят

@pytest.mark.parametrize("message, kind, text", [
    ("[Agent Action] AiogramMessages.send_message({'chat_id': 1})",
     "action", "AiogramMessages.send_message"),
    ("[LLM] Input tokens: 14476.", "llm", ""),
    ("[Vector-Graph RAG] Extracted: 24 vector anchors, 2 graph nodes.", "rag", "24+2"),
    ("[Subconscious] Starting pattern REFLECTION (tick 5)", "subconscious", "reflection"),
    ("[Guard] Rejected call SQLMentalStates.delete", "error", "Gatekeeper: SQLMentalStates.delete"),
])
def test_activity_is_recognised(watcher, monkeypatch, message, kind, text):
    at(5, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, message),
    )

    assert state["activity"]["kind"] == kind
    assert state["activity"]["text"] == text
    assert state["activity"]["title"], "у каждого занятия должна быть русская подпись"


def test_failed_action_is_reported_as_an_error(watcher, monkeypatch):
    at(5, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, "[Agent Action Result] HostOSEditor.write (Error): False"))

    assert state["activity"]["kind"] == "error"


def test_successful_action_does_not_look_like_an_error(watcher, monkeypatch):
    at(5, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, "[Agent Action] SQLDrives.satisfy_drive({'amount': 25})"),
        line(2, "[Agent Action Result] SQLDrives.satisfy_drive (Success): True"))

    assert state["activity"]["kind"] == "action"
    assert not state["lastError"]


def test_llm_failure_is_remembered(watcher, monkeypatch):
    at(5, monkeypatch)
    state = watcher.append(
        line(0, "[LLM] Fatal API error: 401 Unauthorized", level="ERROR"))

    assert state["activity"]["kind"] == "error"
    assert "401" in state["lastError"]


# ---------------------------------------------------------------- всплески

def test_history_does_not_produce_beats(watcher, monkeypatch):
    """
    При открытии консоли мы восстанавливаемся по хвосту журнала. Всплески за
    прошедшее рисовать нельзя — иначе кардиограмма выдаст очередь ударов,
    которых пользователь не застал.
    """
    watcher.log_file.write_text(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m).")
        + line(1, "[ReAct] Step 1/8.")
        + line(2, "[Agent Action] SQLNotes.create({})"),
        encoding="utf-8")

    at(5, monkeypatch)
    state = watcher.poll()

    assert state["step"] == 1, "состояние восстановлено"
    assert state["events"] == [], "но всплесков за прошлое быть не должно"


def test_new_lines_produce_beats_with_growing_seq(watcher, monkeypatch):
    at(5, monkeypatch)
    watcher.append(line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."))

    at(10, monkeypatch)
    state = watcher.append(
        line(6, "[ReAct] Step 1/8."),
        line(7, "[Agent Action] SQLNotes.create({})"),
    )

    seqs = [e["seq"] for e in state["events"]]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    assert [e["kind"] for e in state["events"]] == ["step", "action"]


def test_wakeup_beat_carries_the_event_level(watcher, monkeypatch):
    """Уровень задаёт и высоту всплеска, и цвет ленты — он должен доехать до клиента."""
    at(5, monkeypatch)
    watcher.poll()

    at(10, monkeypatch)
    state = watcher.append(
        line(6, "[Heartbeat] Incoming wakeup event: 'AIOGRAM_MESSAGE_INCOMING' (CRITICAL). Invoking LLM."))

    beat = state["events"][-1]
    assert beat["kind"] == "wake" and beat["level"] == "CRITICAL"
    assert beat["amp"] == pytest.approx(1.0)


def test_beats_are_capped(watcher, monkeypatch):
    at(5, monkeypatch)
    watcher.poll()

    at(500, monkeypatch)
    rows = [line(10 + i, "[Agent Action] SQLNotes.create({})") for i in range(120)]
    state = watcher.append(*rows)

    assert len(state["events"]) == tick.EVENTS_KEPT, "очередь всплесков должна быть ограничена"


# ---------------------------------------------------------------- журнал

def test_rotation_restarts_the_reader(watcher, monkeypatch):
    at(5, monkeypatch)
    watcher.append(line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."))

    # ротация: файл заменён коротким
    watcher.log_file.write_text(line(1, "[ReAct] Step 2/8."), encoding="utf-8")
    at(10, monkeypatch)
    state = watcher.poll()

    assert state["step"] == 2, "после ротации чтение должно начаться сначала"


def test_missing_log_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "LOG_FILE", tmp_path / "нет.log")
    state = tick.TickWatcher().poll()

    assert state["ok"] is True and state["known"] is False
    assert state["note"]


def test_multiline_thoughts_do_not_break_parsing(watcher, monkeypatch):
    """Блок [Thoughts] продолжается строками без отметки времени."""
    at(5, monkeypatch)
    state = watcher.append(
        line(0, "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: m)."),
        line(1, "[ReAct] Step 2/8."),
        line(2, "[Thoughts]:"),
        "[Observation]: Получен плановый сигнал Heartbeat.\n",
        "\n",
        "[Reasoning]: 2026-08-25 это не отметка времени, а текст.\n",
        line(3, "[Agent Action] SQLNotes.create({})"),
    )

    assert state["step"] == 2
    assert state["activity"]["text"] == "SQLNotes.create"


# ---------------------------------------------------------------- длительности

@pytest.mark.parametrize("seconds", [0, 59, 60, 3599, 3600, 86399, 86400, 200000])
def test_duration_parsing_round_trips(seconds):
    """Обратное преобразование к формату фреймворка — сверяем с ним же."""
    from src.utils.dtime import seconds_to_duration_str

    assert tick.parse_duration(seconds_to_duration_str(seconds)) == seconds


def test_duration_parsing_survives_garbage():
    assert tick.parse_duration("не время") is None


# ------------------------------------------- сверка шаблонов с самим фреймворком

HEARTBEAT_SRC = None


def _framework_text(relative):
    from src.web import config_io as cio
    return (cio.ROOT_DIR / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("pattern, sample", [
    (tick.WAKEUP_RE,
     "[Heartbeat] Incoming wakeup event: 'X_EVENT' (CRITICAL). Invoking LLM."),
    (tick.ACCEL_RE,
     "[Heartbeat] Incoming event: 'X_EVENT' (LOW). Next LLM execution scheduled "
     "sooner by 1.0 sec. Until wakeup: 2.0 sec."),
    (tick.DURING_RE,
     "[Heartbeat] Incoming event 'X_EVENT' (HIGH) received during agent execution. "
     "Data appended to context."),
    (tick.INTERRUPT_RE,
     "[Heartbeat] Interrupted current ReAct cycle due to event: X_EVENT (CRITICAL)"),
    (tick.CUSTOM_SLEEP_RE,
     "[Heartbeat] Custom sleep mode engaged for 01:00:00 (depth: 'deep')."),
    (tick.CYCLE_INIT_RE,
     "[ReAct] Reasoning cycle initialized. Reason: HEARTBEAT (LLM Model: some/model)."),
    (tick.STEP_RE, "[ReAct] Step 1/8."),
    (tick.CONCLUDE_RE, "[ReAct] Empty actions list received. Concluding cycle."),
    (tick.CONCLUDE_RE,
     "[ReAct] Early loop termination requested by skill (sleep/shutdown). Concluding cycle."),
    (tick.CANCELLED_RE, "[System] Current ReAct cycle successfully cancelled."),
])
def test_patterns_match_their_samples(pattern, sample):
    assert pattern.search(sample), "шаблон разошёлся с образцом: %s" % sample


@pytest.mark.parametrize("phrase, where", [
    ("Incoming wakeup event:", "src/l3_agent/heartbeat.py"),
    ("Next LLM execution scheduled sooner by", "src/l3_agent/heartbeat.py"),
    ("received during agent execution", "src/l3_agent/heartbeat.py"),
    ("Interrupted current ReAct cycle due to event:", "src/l3_agent/heartbeat.py"),
    ("Custom sleep mode engaged for", "src/l3_agent/heartbeat.py"),
    ("Orchestrator stopped.", "src/l3_agent/heartbeat.py"),
    ("Reasoning cycle initialized. Reason:", "src/l3_agent/react/loop.py"),
    ("Empty actions list received. Concluding cycle.", "src/l3_agent/react/loop.py"),
])
def test_markers_still_exist_in_the_framework(phrase, where):
    """
    Шапка держится на формулировках чужого кода. Если их поменяют, тест упадёт
    здесь — а не молча в интерфейсе, где это выглядит как «агент замер».
    """
    assert phrase in _framework_text(where), "формулировка исчезла из %s" % where


def test_next_tick_is_still_armed_from_the_interval():
    """
    Проверяем саму формулу: следующий такт назначается как «сейчас + интервал».
    Если фреймворк начнёт считать иначе, наш отсчёт станет враньём.
    """
    source = _framework_text("src/l3_agent/heartbeat.py")
    assert re.search(r"_next_tick_time\s*=\s*time\.time\(\)\s*\+\s*self\.heartbeat_interval",
                     source), "формула следующего такта изменилась"


# ---------------------------------------------------------------- подъём агента

def test_boot_is_not_reported_as_work(watcher, monkeypatch):
    """
    pid-файл появляется на первой секунде, а модель эмбеддингов на холодном
    кэше качается минутами. Всё это время консоль писала «АГЕНТ РАБОТАЕТ».
    """
    at(30, monkeypatch)
    state = watcher.append(
        line(0, "[System] Initializing JAWL v0.16.1.2-beta (PID: 15200).", logger="JAWL"),
        line(1, "[Vector DB] Initializing local embedding model: intfloat/multilingual-e5-large.",
             logger="JAWL"),
    )

    assert state["phase"] == "starting"
    assert "эмбеддинг" in state["bootStep"]
    assert "multilingual-e5-large" in state["bootStep"], "не видно, что именно качается"


def test_boot_ends_when_the_framework_says_so(watcher, monkeypatch):
    at(200, monkeypatch)
    state = watcher.append(
        line(0, "[System] Initializing JAWL v0.16.1.2-beta (PID: 15200).", logger="JAWL"),
        line(1, "[Vector DB] Initializing local embedding model: X.", logger="JAWL"),
        line(158, "[Vector DB] Embedding model is ready (path: ...).", logger="JAWL"),
        line(166, "[System] JAWL started successfully. Agent name: Tess", logger="JAWL"),
    )

    assert state["phase"] == "sleep", "подъём не закончился"
    assert state["bootStep"] == "", "шаг подъёма не сброшен"


def test_boot_steps_are_named(watcher, monkeypatch):
    at(20, monkeypatch)
    state = watcher.append(
        line(0, "[System] Initializing JAWL v1 (PID: 1).", logger="JAWL"),
        line(2, "[SQL DB] Database successfully initialized.", logger="JAWL"),
    )

    assert state["bootStep"] == "реляционная база"


def test_shutdown_clears_the_boot_step(watcher, monkeypatch):
    at(20, monkeypatch)
    state = watcher.append(
        line(0, "[System] Initializing JAWL v1 (PID: 1).", logger="JAWL"),
        line(1, "[Vector DB] Initializing local embedding model: X.", logger="JAWL"),
        line(5, "[System] Shutdown complete.", logger="JAWL"),
    )

    assert state["phase"] == "off" and state["bootStep"] == ""

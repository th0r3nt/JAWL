# -*- coding: utf-8 -*-
"""
Состояние такта, восстановленное из журнала.

Агент держит своё состояние (`AgentState` и `Heartbeat._next_tick_time`) в
памяти собственного процесса и никуда его не выкладывает. Консоль — отдельный
процесс, читать чужую память ей нечем. Поэтому шапка восстанавливает картину по
`logs/main.log`: какие строки пишет фреймворк, такие мы и разбираем.

Момент следующего пробуждения фреймворк назначает так
(`src/l3_agent/heartbeat.py`):

* по завершении цикла   — `_next_tick_time = <конец цикла> + heartbeat_interval`;
* при своём сне         — `<момент> + duration` (и интервал уже не применяется);
* при событии-ускорителе — остаток умножается на множитель уровня, и в журнал
  пишется готовое «Until wakeup: N sec» — это самый точный якорь, его и берём;
* при перебивании цикла — пробуждение немедленное.

Здесь повторена ровно эта логика. Единственное место, где журнал молчит, —
цикл, исчерпавший лимит шагов: `while` в `react/loop.py` выходит без записи.
Такое встречается редко (2 цикла из 110 в наблюдаемом журнале), и обходится оно
явной эвристикой — см. `_settle_exhausted`.

Отметки времени в журнале ставит `logging.Formatter` в местном времени той же
машины, поэтому сравнение с `datetime.now()` без зоны корректно.
"""

from __future__ import annotations

import re
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, Optional, Tuple

from src.web import config_io as cio
from src.web import logs

# ---------------------------------------------------------------- разбор строк

LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) - (\S+) - (\w+) - (.*)$")

CYCLE_INIT_RE = re.compile(
    r"\[ReAct\] Reasoning cycle initialized\. Reason: (\S+) \(LLM Model: (.+?)\)\.")
STEP_RE = re.compile(r"\[ReAct\] Step (\d+)/(\d+)\.")
CONCLUDE_RE = re.compile(r"\[ReAct\].*Concluding cycle\.")
CANCELLED_RE = re.compile(r"\[System\] Current ReAct cycle successfully cancelled\.")

WAKEUP_RE = re.compile(
    r"\[Heartbeat\] Incoming wakeup event: '([^']+)' \((\w+)\)\. Invoking LLM\.")
ACCEL_RE = re.compile(
    r"\[Heartbeat\] Incoming event: '([^']+)' \((\w+)\)\..*?Until wakeup: ([\d.]+) sec\.")
DURING_RE = re.compile(
    r"\[Heartbeat\] Incoming event '([^']+)' \((\w+)\) received during agent execution")
INTERRUPT_RE = re.compile(
    r"\[Heartbeat\] Interrupted current ReAct cycle due to event: (\S+) \((\w+)\)")
CUSTOM_SLEEP_RE = re.compile(
    r"\[Heartbeat\] Custom sleep mode engaged for (.+?) \(depth: '(\w+)'\)\.")
ORCH_STOP_RE = re.compile(r"\[Heartbeat\] Orchestrator stopped\.")
AUTONOMOUS_RE = re.compile(r"\[Heartbeat\] Agent switched to autonomous mode\.")

STARTED_RE = re.compile(r"\[System\] JAWL started successfully")
SHUTDOWN_RE = re.compile(r"\[System\] (Initiating JAWL shutdown|Shutdown complete)")

# Подъём агента. pid-файл появляется на первой же секунде, а до готовности
# проходят минуты: модель эмбеддингов на холодном кэше качается долго. По одному
# лишь pid-файлу консоль объявляла бы агента работающим всё это время.
BOOT_RE = re.compile(r"\[System\] Initializing JAWL")
EMBEDDING_START_RE = re.compile(
    r"\[Vector DB\] Initializing local embedding model:\s*(\S+?)\.?\s*$")
EMBEDDING_READY_RE = re.compile(r"\[Vector DB\] Embedding model is ready")

# Шаги подъёма, которые стоит показать: остальное пролетает мгновенно.
BOOT_STEPS = (
    (re.compile(r"\[SQL DB\] Database successfully initialized"), "реляционная база"),
    (re.compile(r"\[Graph DB\] Kuzu database successfully initialized"), "граф знаний"),
    (re.compile(r"\[Vector DB\] Database initialized"), "векторная база"),
    (re.compile(r"\[System\] Initializing L\d"), "слои фреймворка"),
    (re.compile(r"Interface loaded"), "интерфейсы"),
)

ACTION_RE = re.compile(r"\[Agent Action\] (\w+)\.(\w+)\(")
ACTION_RESULT_RE = re.compile(r"\[Agent Action Result\] (\w+)\.(\w+) \((\w+)\)")
LLM_IN_RE = re.compile(r"\[LLM\] Input tokens: (\d+)")
LLM_OUT_RE = re.compile(r"\[LLM\] Output tokens: (\d+)")
THOUGHTS_RE = re.compile(r"\[Thoughts\]:")
RAG_RE = re.compile(r"\[Vector-Graph RAG\] Extracted: (\d+) vector anchors, (\d+) graph nodes")
SUBC_RE = re.compile(r"\[Subconscious\] Starting pattern (\w+)")
SWARM_RE = re.compile(r"\[Subagent ReAct\] Step (\d+)/(\d+)")
GUARD_RE = re.compile(r"\[Guard\] Rejected call (\S+)")
TOT_RE = re.compile(r"\[ToT\]")

# ошибки, на которые шапка должна реагировать заметно
ERROR_RE = re.compile(
    r"\[LLM\] (Fatal API error|Invalid API key|Rate Limit)"
    r"|\[ReAct\] JSON parse error"
    r"|\[System\] Critical error")

DURATION_RE = re.compile(r"(?:(\d+)\s+\S+,\s*)?(\d{2}):(\d{2}):(\d{2})")

# «01:15:00» и «2 дня, 03:00:00» — формат seconds_to_duration_str
def parse_duration(text: str) -> Optional[int]:
    """Обратное преобразование к `src/utils/dtime.seconds_to_duration_str`."""
    match = DURATION_RE.search(text)
    if not match:
        return None
    days, hours, minutes, seconds = match.groups()
    return (int(days or 0) * 86400 + int(hours) * 3600
            + int(minutes) * 60 + int(seconds))


# русские подписи действий: в шапке мало места, длинный Class.method не влезает
ACTIVITY_TITLES = {
    "llm": "запрос к модели",
    "thinking": "размышляет",
    "rag": "поиск в памяти",
    "action": "действие",
    "subconscious": "подсознание",
    "swarm": "рой",
    "tot": "дерево мыслей",
    "error": "ошибка",
    "idle": "ожидание",
}

# уровень события -> высота всплеска на кардиограмме
BEAT_AMPLITUDE = {
    "CRITICAL": 1.0,
    "HIGH": 0.85,
    "MEDIUM": 0.66,
    "LOW": 0.52,
    "BACKGROUND": 0.42,
    "INFO": 0.36,
}

EVENTS_KEPT = 40          # столько последних всплесков помним для клиента
BOOTSTRAP_BYTES = 96 * 1024   # хвост, по которому восстанавливаемся при старте

# Цикл, исчерпавший лимит шагов, завершается без записи в журнал. Признаём его
# законченным, только когда модель на последнем шаге уже ответила и после этого
# наступила тишина: сам запрос к модели занимает секунды и молчит в журнале.
EXHAUSTED_QUIET_SEC = 20.0


class TickWatcher:
    """
    Инкрементальный разбор журнала.

    Держит собственное смещение, независимое от вкладки «Логи»: там свой курсор
    и своя частота опроса.
    """

    def __init__(self) -> None:
        self.reset()

    # ------------------------------------------------------------------ жизнь

    def reset(self) -> None:
        self._offset = 0
        self._bootstrapped = False

        self.phase = "unknown"           # wake | sleep | starting | off | unknown
        self.boot_step = ""              # чем занят подъём агента
        self.step = 0
        self.max_steps = 0
        self.reason = ""
        self.level = ""
        self.model = ""

        self.wake_at: Optional[datetime] = None
        self.sleep_depth = "normal"
        self.cycle_started: Optional[datetime] = None

        self.activity_kind = "idle"
        self.activity_text = ""
        self.activity_at: Optional[datetime] = None

        self.last_line_at: Optional[datetime] = None
        self.last_error = ""
        self.last_error_at: Optional[datetime] = None

        self._llm_answered = False       # модель ответила на текущем шаге
        self._cycle_custom_sleep = False  # цикл начался из своего сна
        self._events: Deque[Dict[str, Any]] = deque(maxlen=EVENTS_KEPT)
        self._seq = 0

        self._config_cache: Tuple[int, bool, int] = (0, False, 0)
        self._config_stamp = -1

    # ------------------------------------------------------------- настройки

    def _config(self) -> Tuple[int, bool, int]:
        """
        Интервал такта, непрерывный режим и лимит шагов из settings.yaml.

        Значения нужны на каждой разбираемой строке, а разбор хвоста — это
        тысячи строк. Держим разобранный конфиг до изменения файла: интервал
        фреймворк подхватывает на ходу (`Heartbeat.update_config`), так что
        перечитать его надо, но не по тысяче раз на пакет.
        """
        try:
            stamp = cio.SETTINGS_FILE.stat().st_mtime_ns
        except OSError:
            return self._config_cache

        if stamp == self._config_stamp:
            return self._config_cache

        try:
            settings = cio.load_yaml(cio.SETTINGS_FILE)
            self._config_cache = (
                int(cio.get_path(settings, "system.heartbeat_interval", 0) or 0),
                bool(cio.get_path(settings, "system.continuous_cycle", False)),
                int(cio.get_path(settings, "llm.max_react_steps", 0) or 0),
            )
            self._config_stamp = stamp
        except Exception:                                    # noqa: BLE001
            pass
        return self._config_cache

    # ---------------------------------------------------------------- события

    def _beat(self, kind: str, level: str = "", text: str = "",
              at: Optional[datetime] = None) -> None:
        """Всплеск для кардиограммы. Клиент рисует только то, чего ещё не видел."""
        self._seq += 1
        self._events.append({
            "seq": self._seq,
            "kind": kind,
            "level": level,
            "text": text,
            "amp": BEAT_AMPLITUDE.get(level, 0.6 if kind == "step" else 0.34),
            "at": at.isoformat(timespec="milliseconds") if at else None,
        })

    def _activity(self, kind: str, text: str, at: datetime) -> None:
        self.activity_kind = kind
        self.activity_text = text
        self.activity_at = at

    # ----------------------------------------------------------------- разбор

    def _consume(self, text: str, quiet: bool) -> None:
        """
        Прогоняет новые строки через состояние.

        `quiet` — восстановление по хвосту при первом чтении: всплески за
        прошлое рисовать не надо, иначе кардиограмма выдаст пачку ударов,
        которых пользователь не застал.
        """
        interval, continuous, _ = self._config()   # один раз на пакет, не на строку

        for raw in text.splitlines():
            match = LINE_RE.match(raw)
            if not match:
                continue                    # продолжение [Thoughts] и прочий текст
            stamp, _logger, level_name, message = match.groups()
            try:
                when = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                continue

            self.last_line_at = when
            self._apply(message, when, level_name, quiet, interval, continuous)

    def _apply(self, message: str, when: datetime, level_name: str,
               quiet: bool, interval: int, continuous: bool) -> None:

        # ---- жизненный цикл процесса
        if SHUTDOWN_RE.search(message) or ORCH_STOP_RE.search(message):
            self.phase = "off"
            self.step = 0
            self.boot_step = ""
            self.wake_at = None
            self._activity("idle", "", when)
            return

        if STARTED_RE.search(message) or AUTONOMOUS_RE.search(message):
            self.phase = "sleep"
            self.boot_step = ""                        # подъём закончился
            if interval:
                self.wake_at = when + timedelta(seconds=interval)
            return

        # ---- подъём агента
        if BOOT_RE.search(message):
            self.phase = "starting"
            self.boot_step = "запуск ядра"
            self.step = 0
            self.wake_at = None
            return

        found = EMBEDDING_START_RE.search(message)
        if found:
            self.phase = "starting"
            # на холодном кэше это минуты — самый долгий шаг подъёма
            self.boot_step = "качается модель эмбеддингов: " + found.group(1)
            return

        if EMBEDDING_READY_RE.search(message):
            self.boot_step = "модель эмбеддингов готова"
            return

        if self.phase == "starting":
            for pattern, title in BOOT_STEPS:
                if pattern.search(message):
                    self.boot_step = title
                    return

        # ---- пробуждение и ускорение сна
        found = WAKEUP_RE.search(message)
        if found:
            self.reason, self.level = found.group(1), found.group(2)
            self.wake_at = when
            if not quiet:
                self._beat("wake", self.level, self.reason, when)
            return

        found = ACCEL_RE.search(message)
        if found:
            # журнал уже посчитал остаток за нас — точнее якоря нет
            self.wake_at = when + timedelta(seconds=float(found.group(3)))
            if not quiet:
                self._beat("accel", found.group(2), found.group(1), when)
            return

        found = CUSTOM_SLEEP_RE.search(message)
        if found:
            seconds = parse_duration(found.group(1))
            self.sleep_depth = found.group(2)
            self.phase = "sleep"
            if seconds is not None:
                self.wake_at = when + timedelta(seconds=seconds)
            return

        found = DURING_RE.search(message)
        if found:
            if not quiet:
                self._beat("event", found.group(2), found.group(1), when)
            return

        found = INTERRUPT_RE.search(message)
        if found:
            # перебитый цикл будит агента немедленно
            self.wake_at = when
            if not quiet:
                self._beat("interrupt", found.group(2), found.group(1), when)
            return

        # ---- цикл рассуждения
        found = CYCLE_INIT_RE.search(message)
        if found:
            self.phase = "wake"
            self.reason, self.model = found.group(1), found.group(2)
            self.cycle_started = when
            self.step = 0
            # фреймворк запоминает признак своего сна на входе в цикл и по нему
            # решает, назначать ли следующий такт по интервалу
            self._cycle_custom_sleep = self.sleep_depth != "normal"
            self._llm_answered = False
            self._activity("thinking", "", when)
            return

        found = STEP_RE.search(message)
        if found:
            step, total = int(found.group(1)), int(found.group(2))
            if step != self.step:               # строка дублируется двумя логгерами
                self.step, self.max_steps = step, total
                self._llm_answered = False
                if not quiet:
                    self._beat("step", "", "шаг %d/%d" % (step, total), when)
            self.phase = "wake"
            return

        if CONCLUDE_RE.search(message):
            self._end_cycle(when, interval, continuous)
            return

        if CANCELLED_RE.search(message):
            # отмена — это перебивание событием: следующий цикл начнётся сразу
            self.phase = "sleep"
            self.step = 0
            self.wake_at = when
            self._activity("idle", "", when)
            return

        # ---- чем занят прямо сейчас
        if ERROR_RE.search(message) or level_name in ("ERROR", "CRITICAL"):
            self.last_error = message[:200]
            self.last_error_at = when
            self._activity("error", message[:120], when)
            if not quiet:
                self._beat("error", "", message[:80], when)
            return

        found = ACTION_RE.search(message)
        if found:
            self._activity("action", "%s.%s" % found.groups(), when)
            if not quiet:
                self._beat("action", "", "%s.%s" % found.groups(), when)
            return

        found = ACTION_RESULT_RE.search(message)
        if found:
            outcome = found.group(3)
            if outcome.lower() != "success":
                self._activity("error", "%s.%s не выполнилось" % found.groups()[:2], when)
                if not quiet:
                    self._beat("error", "", "%s.%s" % found.groups()[:2], when)
            return

        if LLM_IN_RE.search(message):
            self._llm_answered = False
            self._activity("llm", "", when)
            return

        if LLM_OUT_RE.search(message):
            self._llm_answered = True
            return

        if THOUGHTS_RE.search(message):
            self._llm_answered = True
            self._activity("thinking", "", when)
            return

        found = RAG_RE.search(message)
        if found:
            self._activity("rag", "%s+%s" % found.groups(), when)
            return

        found = SUBC_RE.search(message)
        if found:
            self._activity("subconscious", found.group(1).lower(), when)
            return

        found = SWARM_RE.search(message)
        if found:
            self._activity("swarm", "шаг %s/%s" % found.groups(), when)
            return

        found = GUARD_RE.search(message)
        if found:
            self._activity("error", "Gatekeeper: %s" % found.group(1), when)
            if not quiet:
                self._beat("error", "", "Gatekeeper", when)
            return

        if TOT_RE.search(message):
            self._activity("tot", "", when)

    def _end_cycle(self, when: datetime, interval: int, continuous: bool) -> None:
        """
        Конец цикла: отсюда фреймворк отсчитывает следующий такт.

        Если цикл начинался из своего сна, `_next_tick_time` он не пересчитывает
        — только сбрасывает глубину. Момент пробуждения тогда уже в прошлом, и
        следующий такт начнётся сразу; повторяем это, а не подставляем интервал.
        """
        was_custom = self._cycle_custom_sleep
        self.phase = "sleep"
        self.step = 0
        self.sleep_depth = "normal"
        self._cycle_custom_sleep = False
        self._activity("idle", "", when)

        if continuous:
            self.wake_at = when                 # непрерывный режим не спит
        elif was_custom:
            pass                                # момент задан своим сном, он уже прошёл
        elif interval:
            self.wake_at = when + timedelta(seconds=interval)

    def _settle_exhausted(self, now: datetime, interval: int,
                          continuous: bool) -> None:
        """
        Цикл, упёршийся в лимит шагов, завершается без строки в журнале.

        Признаём его законченным, только если модель на последнем шаге уже
        ответила и после этого журнал молчит: пока идёт запрос к модели, тишина
        в журнале — это норма, а не конец такта.
        """
        if self.phase != "wake" or not self.max_steps:
            return
        if self.step < self.max_steps or not self._llm_answered:
            return
        if self.last_line_at is None:
            return
        if (now - self.last_line_at).total_seconds() < EXHAUSTED_QUIET_SEC:
            return
        self._end_cycle(self.last_line_at, interval, continuous)

    # ------------------------------------------------------------------ опрос

    def poll(self) -> Dict[str, Any]:
        """Текущее состояние такта. Читает только то, что дописалось с прошлого раза."""
        interval, continuous, config_max = self._config()

        if not logs.exists():
            # Форма ответа должна совпадать с обычной: клиент читает те же поля,
            # и «journal ещё не создан» не повод отдавать урезанный объект.
            answer = self._answer(datetime.now(), interval, continuous, config_max)
            answer["note"] = "журнал ещё не создан"
            return answer

        if not self._bootstrapped:
            text, self._offset = logs.read_tail(BOOTSTRAP_BYTES)
            self._bootstrapped = True
            self._consume(text, quiet=True)        # прошлое не «бьёт» по кардиограмме
        else:
            total = logs.size()
            if total < self._offset:               # ротация — начинаем сначала
                self._offset = 0
            text, self._offset = logs.read_since(self._offset)
            if text:
                self._consume(text, quiet=False)

        now = datetime.now()
        self._settle_exhausted(now, interval, continuous)

        return self._answer(now, interval, continuous, config_max)

    def _answer(self, now: datetime, interval: int, continuous: bool,
                config_max: int) -> Dict[str, Any]:
        """Ответ одной формы для всех случаев — клиент читает одни и те же поля."""
        wake_in = None
        if self.phase == "sleep" and self.wake_at is not None:
            wake_in = max(0.0, (self.wake_at - now).total_seconds())
            if continuous:
                wake_in = 0.0

        return {
            "ok": True,
            "known": self.phase != "unknown",
            "phase": self.phase,
            "step": self.step,
            "maxSteps": self.max_steps or config_max,
            "reason": self.reason,
            "level": self.level,
            "model": self.model,
            "wakeInSec": wake_in,
            "wakeAt": self.wake_at.isoformat(timespec="seconds") if self.wake_at else None,
            "intervalSec": interval,
            "continuous": continuous,
            "sleepDepth": self.sleep_depth,
            "bootStep": self.boot_step,
            "activity": {
                "kind": self.activity_kind,
                "title": ACTIVITY_TITLES.get(self.activity_kind, self.activity_kind),
                "text": self.activity_text,
                "at": self.activity_at.isoformat(timespec="seconds") if self.activity_at else None,
                "ageSec": ((now - self.activity_at).total_seconds()
                           if self.activity_at else None),
            },
            "lastError": self.last_error,
            "lastErrorAt": (self.last_error_at.isoformat(timespec="seconds")
                            if self.last_error_at else None),
            "lastLineAt": (self.last_line_at.isoformat(timespec="seconds")
                           if self.last_line_at else None),
            "events": list(self._events),
            "seq": self._seq,
        }


_watcher: Optional[TickWatcher] = None


def watcher() -> TickWatcher:
    """Один разбор на процесс: смещение и состояние должны переживать запросы."""
    global _watcher
    if _watcher is None:
        _watcher = TickWatcher()
    return _watcher


def state() -> Dict[str, Any]:
    return watcher().poll()

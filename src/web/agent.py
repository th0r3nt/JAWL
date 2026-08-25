# -*- coding: utf-8 -*-
"""
Запуск и остановка агента из веб-консоли.

Механизм тот же, что у CLI (`src/cli/screens/agent_control.py`), и намеренно
не дублирует его логику там, где можно переиспользовать:

* проверка «работает ли» сделана здесь заново и только на чтение: штатная
  `is_agent_running()` при отрицательном ответе удаляет pid- и lock-файлы,
  а консоль опрашивает состояние по таймеру и снесла бы их не вовремя;
* остановка идёт через файл-сигнал `agent.stop`, который ловит сам фреймворк
  (в логах это «[System] Received stop file signal»);
* если за отведённое время процесс не ушёл, он снимается принудительно.

Ядро при этом не изменяется — только читается.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

import psutil

from src.web import config_io as cio

ROOT_DIR = cio.ROOT_DIR
DATA_DIR = ROOT_DIR / "src" / "utils" / "local" / "data"
PID_FILE = DATA_DIR / "agent.pid"
STOP_FILE = DATA_DIR / "agent.stop"
LOCK_FILE = DATA_DIR / "agent.lock"
MAIN_SCRIPT = ROOT_DIR / "src" / "main.py"
CRASH_LOG = ROOT_DIR / "logs" / "startup" / "startup_error.log"

START_GRACE_SEC = 5      # столько ждём, чтобы поймать падение сразу после старта
STOP_TIMEOUT_SEC = 15    # столько даём на корректное завершение


def _pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:                                  # noqa: BLE001
        return None


_launched: subprocess.Popen | None = None      # процесс, поднятый этой консолью
_owned = False                                 # мы его запустили — нам и гасить
_pid_seen = False                              # для этого запуска pid-файл уже появлялся


def owns_agent() -> bool:
    """
    Запускала ли агента именно эта консоль.

    Важно для остановки при закрытии окна: агента могли поднять из CLI ещё до
    старта консоли, и гасить чужой процесс мы не вправе.
    """
    return _owned and status()["running"]


def _alive(pid: int | None) -> bool:
    """Жив ли процесс с таким pid и похож ли он на python."""
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and "python" in (proc.name() or "").lower()
    except Exception:                                  # noqa: BLE001
        return False


def status() -> Dict[str, Any]:
    """
    Состояние процесса агента — только чтением, без побочных эффектов.

    Штатная `is_agent_running()` при отрицательном ответе удаляет pid- и
    lock-файлы. Консоль опрашивает статус каждые несколько секунд, и такой
    опрос мог бы снести файлы ровно в тот момент, когда агент их создаёт.
    Поэтому здесь только чтение pid-файла и проверка процесса.

    Отдельное состояние `starting`: между запуском процесса и появлением
    pid-файла проходит время, и всё это время агент уже поднимается.

    И отдельное `stopping`. Без него завершение выглядело как запуск: агент
    удаляет pid-файл последней строкой (`[System] PID files deleted`), но сам
    процесс после этого ещё сворачивается секунду-другую. В это окно
    «pid-файла нет, процесс жив» неотличимо от старта — если не помнить, что
    для этого запуска pid-файл уже появлялся.
    """
    global _pid_seen

    pid = _pid()
    running = _alive(pid)
    if running:
        _pid_seen = True

    ours_alive = _launched is not None and _launched.poll() is None
    starting = not running and ours_alive and not _pid_seen
    stopping = not running and ours_alive and _pid_seen

    uptime = None
    if running:
        try:
            uptime = int(time.time() - psutil.Process(pid).create_time())
        except Exception:                              # noqa: BLE001
            uptime = None

    return {
        "ok": True,
        # процесс ещё жив — для кнопок это «работает»: второго поднимать нельзя
        "running": running or starting or stopping,
        "starting": starting,
        "stopping": stopping,
        "pid": pid if running else (_launched.pid if ours_alive else None),
        "uptimeSec": uptime,
    }


def _validate_config() -> str | None:
    """Ранняя проверка конфигов: понятная ошибка лучше падения через 5 секунд."""
    try:
        from src.utils.settings import load_config
        load_config()
        return None
    except Exception as exc:                           # noqa: BLE001
        return "конфигурация не проходит проверку: %s" % exc


def start() -> Dict[str, Any]:
    """Поднимает src/main.py отдельным процессом, как это делает CLI."""
    global _launched, _owned, _pid_seen

    if status()["running"]:
        return {"ok": False, "error": "агент уже запущен"}

    _pid_seen = False                          # для нового запуска отсчёт заново

    problem = _validate_config()
    if problem:
        return {"ok": False, "error": problem}

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.unlink(missing_ok=True)                  # иначе агент сразу выключится

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)
    env["PYTHONIOENCODING"] = "utf-8"

    kwargs: Dict[str, Any] = {"close_fds": True}
    if os.name == "nt":
        # своя группа процессов + без окна консоли
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
    else:
        kwargs["start_new_session"] = True

    try:
        with open(CRASH_LOG, "w", encoding="utf-8") as err:
            process = subprocess.Popen(
                [sys.executable, str(MAIN_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=err,
                cwd=str(ROOT_DIR),
                env=env,
                **kwargs,
            )
    except Exception as exc:                           # noqa: BLE001
        return {"ok": False, "error": "не удалось запустить процесс: %s" % exc}

    _launched = process
    _owned = True
    time.sleep(START_GRACE_SEC)

    if process.poll() is not None:
        _launched = None
        _owned = False
        tail = ""
        try:
            tail = CRASH_LOG.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:                              # noqa: BLE001
            pass
        tail = tail.splitlines()[-6:] if tail else []
        return {
            "ok": False,
            "error": "агент упал сразу после запуска",
            "detail": "\n".join(tail),
        }

    return {"ok": True, "pid": process.pid}


def stop(timeout: int | None = None) -> Dict[str, Any]:
    """Просит агента завершиться, при отказе снимает процесс."""
    global _launched, _owned, _pid_seen

    state = status()
    if not state["running"]:
        _launched = None
        _owned = False
        _pid_seen = False
        PID_FILE.unlink(missing_ok=True)
        return {"ok": True, "already": True}

    pid = state["pid"]
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.touch(exist_ok=True)

    forced = False
    for _ in range(timeout if timeout is not None else STOP_TIMEOUT_SEC):
        if not _alive(pid) and (_launched is None or _launched.poll() is not None):
            break
        time.sleep(1)
    else:
        forced = True
        for victim in (pid, _launched.pid if _launched else None):
            try:
                if victim:
                    psutil.Process(victim).kill()
            except Exception:                          # noqa: BLE001
                pass

    _launched = None
    _owned = False
    _pid_seen = False
    PID_FILE.unlink(missing_ok=True)
    STOP_FILE.unlink(missing_ok=True)
    if forced:
        # при штатном завершении фреймворк убирает блокировку сам; после
        # принудительного снятия она осталась бы висеть
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            pass                                       # ещё держится — снимется при следующем старте
    return {"ok": True, "forced": forced}

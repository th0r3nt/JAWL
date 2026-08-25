# -*- coding: utf-8 -*-
"""
Запуск и остановка агента.

Настоящий процесс не поднимается: subprocess и psutil подменяются. Проверяется
логика — что консоль не трогает файлы фреймворка без нужды, различает состояния
и корректно докладывает об ошибках.
"""

import pytest

from src.web import agent


@pytest.fixture
def sandbox_agent(tmp_path, monkeypatch):
    """Файлы pid/stop и журнал падений уводим во временный каталог."""
    monkeypatch.setattr(agent, "PID_FILE", tmp_path / "agent.pid")
    monkeypatch.setattr(agent, "STOP_FILE", tmp_path / "agent.stop")
    monkeypatch.setattr(agent, "CRASH_LOG", tmp_path / "startup_error.log")
    monkeypatch.setattr(agent, "_launched", None)
    monkeypatch.setattr(agent, "_owned", False)
    # состояние модуля живёт между тестами: без сброса «видели pid» предыдущий
    # тест решал бы за следующий, запуск это или остановка
    monkeypatch.setattr(agent, "_pid_seen", False)
    monkeypatch.setattr(agent, "START_GRACE_SEC", 0)
    monkeypatch.setattr(agent, "STOP_TIMEOUT_SEC", 2)
    return tmp_path


class FakeProcess:
    """Подделка Popen: жив, пока не сказали обратное."""

    def __init__(self, pid=4242, dead=False):
        self.pid = pid
        self._dead = dead
        self.killed = False

    def poll(self):
        return 1 if self._dead else None

    def die(self):
        self._dead = True


# ---------------------------------------------------------------- статус

def test_status_is_stopped_without_pid_file(sandbox_agent):
    state = agent.status()
    assert state == {"ok": True, "running": False, "starting": False,
                     "stopping": False, "pid": None, "uptimeSec": None}


def test_status_does_not_delete_framework_files(sandbox_agent, monkeypatch):
    """
    Штатная is_agent_running() при отрицательном ответе стирает pid и lock.
    Консоль опрашивает статус по таймеру — стереть их она не должна никогда.
    """
    pid_file = sandbox_agent / "agent.pid"
    pid_file.write_text("999999", encoding="utf-8")
    monkeypatch.setattr(agent, "_alive", lambda pid: False)

    agent.status()

    assert pid_file.exists(), "консоль удалила pid-файл фреймворка"


def test_status_reports_running_with_uptime(sandbox_agent, monkeypatch):
    (sandbox_agent / "agent.pid").write_text("1234", encoding="utf-8")
    monkeypatch.setattr(agent, "_alive", lambda pid: pid == 1234)

    class Proc:
        @staticmethod
        def create_time():
            import time
            return time.time() - 90

    monkeypatch.setattr(agent.psutil, "Process", lambda pid: Proc)

    state = agent.status()
    assert state["running"] is True and state["starting"] is False
    assert state["pid"] == 1234
    assert 85 <= state["uptimeSec"] <= 95


def test_starting_state_while_pid_file_is_not_written_yet(sandbox_agent, monkeypatch):
    """
    На первом запуске агент минутами качает модель эмбеддингов и не успевает
    зарегистрироваться. Всё это время он работает, а не «остановлен».
    """
    monkeypatch.setattr(agent, "_launched", FakeProcess(pid=777))

    state = agent.status()
    assert state["running"] is True
    assert state["starting"] is True
    assert state["pid"] == 777


# ---------------------------------------------------------------- запуск

def test_start_refuses_when_already_running(sandbox_agent, monkeypatch):
    (sandbox_agent / "agent.pid").write_text("1234", encoding="utf-8")
    monkeypatch.setattr(agent, "_alive", lambda pid: True)

    res = agent.start()
    assert res["ok"] is False and "уже запущен" in res["error"]


def test_start_refuses_on_broken_config(sandbox_agent, monkeypatch):
    """Понятная ошибка лучше, чем падение процесса через пять секунд."""
    monkeypatch.setattr(agent, "_validate_config", lambda: "конфигурация не проходит проверку: тест")

    res = agent.start()
    assert res["ok"] is False and "не проходит проверку" in res["error"]


def test_start_removes_stale_stop_signal(sandbox_agent, monkeypatch):
    """Забытый agent.stop выключил бы агента сразу после запуска."""
    stop_file = sandbox_agent / "agent.stop"
    stop_file.touch()

    monkeypatch.setattr(agent, "_validate_config", lambda: None)
    monkeypatch.setattr(agent.subprocess, "Popen", lambda *a, **kw: FakeProcess())

    res = agent.start()
    assert res["ok"] is True
    assert not stop_file.exists(), "старый сигнал остановки не убран"


def test_start_reports_immediate_crash_with_log_tail(sandbox_agent, monkeypatch):
    monkeypatch.setattr(agent, "_validate_config", lambda: None)

    def popen(*args, **kwargs):
        (sandbox_agent / "startup_error.log").write_text(
            "строка 1\nстрока 2\nModuleNotFoundError: нет такого модуля\n", encoding="utf-8")
        return FakeProcess(dead=True)

    monkeypatch.setattr(agent.subprocess, "Popen", popen)

    res = agent.start()
    assert res["ok"] is False
    assert "упал сразу после запуска" in res["error"]
    assert "ModuleNotFoundError" in res["detail"], "хвост журнала не приложен"


# ---------------------------------------------------------------- остановка

def test_stop_on_stopped_agent_is_harmless(sandbox_agent):
    res = agent.stop()
    assert res == {"ok": True, "already": True}


def test_stop_asks_politely_first(sandbox_agent, monkeypatch):
    """Сначала файл-сигнал; принудительное снятие — только если не ответил."""
    (sandbox_agent / "agent.pid").write_text("1234", encoding="utf-8")

    seen = {"signal": False}
    alive = {"value": True}

    def fake_alive(pid):
        # агент замечает сигнал и уходит
        if seen["signal"]:
            alive["value"] = False
        return alive["value"]

    monkeypatch.setattr(agent, "_alive", fake_alive)

    real_touch = agent.STOP_FILE.touch

    def touch(**kwargs):
        seen["signal"] = True
        return real_touch(**kwargs)

    monkeypatch.setattr(type(agent.STOP_FILE), "touch", lambda self, **kw: touch(**kw))

    res = agent.stop()
    assert res["ok"] is True
    assert res["forced"] is False, "процесс сняли, хотя он согласился уйти сам"


def test_stop_forces_when_agent_ignores_the_signal(sandbox_agent, monkeypatch):
    (sandbox_agent / "agent.pid").write_text("1234", encoding="utf-8")
    monkeypatch.setattr(agent, "_alive", lambda pid: True)

    killed = []

    class Proc:
        def __init__(self, pid):
            self.pid = pid

        def kill(self):
            killed.append(self.pid)

    monkeypatch.setattr(agent.psutil, "Process", Proc)

    res = agent.stop()
    assert res["forced"] is True
    assert 1234 in killed


def test_stop_cleans_up_its_own_files(sandbox_agent, monkeypatch):
    pid_file = sandbox_agent / "agent.pid"
    pid_file.write_text("1234", encoding="utf-8")
    monkeypatch.setattr(agent, "_alive", lambda pid: False)

    agent.stop()
    assert not pid_file.exists()
    assert not (sandbox_agent / "agent.stop").exists()


def test_forced_stop_removes_stale_lock(sandbox_agent, monkeypatch):
    """
    При штатном завершении блокировку убирает сам фреймворк. После
    принудительного снятия она осталась бы висеть.
    """
    lock = sandbox_agent / "agent.lock"
    lock.touch()
    monkeypatch.setattr(agent, "LOCK_FILE", lock)
    (sandbox_agent / "agent.pid").write_text("1234", encoding="utf-8")
    monkeypatch.setattr(agent, "_alive", lambda pid: True)

    class Proc:
        def __init__(self, pid):
            pass

        def kill(self):
            pass

    monkeypatch.setattr(agent.psutil, "Process", Proc)

    res = agent.stop()
    assert res["forced"] is True
    assert not lock.exists()


def test_graceful_stop_leaves_lock_to_the_framework(sandbox_agent, monkeypatch):
    lock = sandbox_agent / "agent.lock"
    lock.touch()
    monkeypatch.setattr(agent, "LOCK_FILE", lock)
    (sandbox_agent / "agent.pid").write_text("1234", encoding="utf-8")

    seen = {"n": 0}

    def alive(pid):
        seen["n"] += 1
        return seen["n"] < 2          # со второй проверки процесса уже нет

    monkeypatch.setattr(agent, "_alive", alive)

    res = agent.stop()
    assert res["forced"] is False
    assert lock.exists(), "блокировку при штатном выходе трогать не надо"


def test_shutdown_is_not_mistaken_for_startup(sandbox_agent, monkeypatch):
    """
    Агент удаляет pid-файл последней строкой («[System] PID files deleted»), но
    сворачивается ещё секунду-другую. В это окно «pid-файла нет, процесс жив»
    неотличимо от старта — и консоль писала «АГЕНТ ЗАПУСКАЕТСЯ» сразу после
    остановки.
    """
    monkeypatch.setattr(agent, "_launched", FakeProcess(pid=777))
    (sandbox_agent / "agent.pid").write_text("777", encoding="utf-8")
    monkeypatch.setattr(agent, "_alive", lambda pid: True)

    assert agent.status()["running"] is True          # запомнили, что pid был

    # агент стёр pid-файл, но процесс ещё не завершился
    (sandbox_agent / "agent.pid").unlink()
    monkeypatch.setattr(agent, "_alive", lambda pid: False)

    state = agent.status()
    assert state["stopping"] is True
    assert state["starting"] is False, "завершение принято за запуск"
    assert state["running"] is True, "процесс ещё жив — второго поднимать нельзя"


def test_new_launch_forgets_the_previous_pid(sandbox_agent, monkeypatch):
    """После остановки следующий запуск снова должен считаться запуском."""
    monkeypatch.setattr(agent, "_launched", FakeProcess(pid=1))
    (sandbox_agent / "agent.pid").write_text("1", encoding="utf-8")
    monkeypatch.setattr(agent, "_alive", lambda pid: True)
    agent.status()

    monkeypatch.setattr(agent, "_alive", lambda pid: False)
    agent.stop(timeout=1)

    monkeypatch.setattr(agent, "_launched", FakeProcess(pid=2))
    state = agent.status()
    assert state["starting"] is True and state["stopping"] is False

# -*- coding: utf-8 -*-
"""
Окно консоли как индикатор состояния и остановка агента при выходе.

Главное, что здесь проверяется: консоль гасит только того агента, которого
запускала сама. Чужой процесс, поднятый из CLI, закрытие окна пережить обязан.
"""

import pytest

from src.web import agent, console_ui


@pytest.fixture(autouse=True)
def reset_ownership(monkeypatch):
    monkeypatch.setattr(agent, "_owned", False)
    monkeypatch.setattr(agent, "_launched", None)


# ---------------------------------------------------------------- владение

def test_console_does_not_own_a_foreign_agent(monkeypatch):
    """Агент поднят из CLI: консоль его не запускала и трогать не должна."""
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": True,
                                                  "starting": False, "pid": 1,
                                                  "uptimeSec": 5})
    assert agent.owns_agent() is False


def test_console_owns_the_agent_it_started(monkeypatch):
    monkeypatch.setattr(agent, "_owned", True)
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": True,
                                                  "starting": False, "pid": 1,
                                                  "uptimeSec": 5})
    assert agent.owns_agent() is True


def test_ownership_drops_when_agent_is_gone(monkeypatch):
    monkeypatch.setattr(agent, "_owned", True)
    monkeypatch.setattr(agent, "status", lambda: {"ok": True, "running": False,
                                                  "starting": False, "pid": None,
                                                  "uptimeSec": None})
    assert agent.owns_agent() is False


# ---------------------------------------------------------------- выход

def test_exit_leaves_foreign_agent_alone(monkeypatch, capsys):
    """
    Консоль открыли посмотреть настройки, пока агент уже работал.
    Закрытие окна не должно ронять чужой процесс.
    """
    stopped = []
    monkeypatch.setattr(agent, "owns_agent", lambda: False)
    monkeypatch.setattr(agent, "stop", lambda **kw: stopped.append(kw) or {"ok": True})

    console_ui.shutdown_owned_agent()

    assert stopped == [], "остановлен агент, которого консоль не запускала"
    assert capsys.readouterr().out == ""


def test_exit_stops_own_agent(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(agent, "owns_agent", lambda: True)
    monkeypatch.setattr(agent, "stop",
                        lambda timeout=None: calls.append(timeout) or {"ok": True, "forced": False})

    console_ui.shutdown_owned_agent(timeout=4)

    assert calls == [4], "не передан укороченный таймаут закрытия окна"
    assert "остановлен" in capsys.readouterr().out


def test_exit_reports_forced_kill(monkeypatch, capsys):
    monkeypatch.setattr(agent, "owns_agent", lambda: True)
    monkeypatch.setattr(agent, "stop", lambda **kw: {"ok": True, "forced": True})

    console_ui.shutdown_owned_agent()

    assert "принудительно" in capsys.readouterr().out


# ---------------------------------------------------------------- строка состояния

@pytest.mark.parametrize("state, expect_key, expect_text, expect_color", [
    ({"running": False, "starting": False, "pid": None, "uptimeSec": None},
     "stopped", "ОСТАНОВЛЕН", console_ui.RED),
    ({"running": True, "starting": True, "pid": 7, "uptimeSec": None},
     "starting", "ЗАПУСКАЕТСЯ", console_ui.YELLOW),
    ({"running": True, "starting": False, "pid": 7, "uptimeSec": 3725},
     "running", "РАБОТАЕТ", console_ui.GREEN),
])
def test_status_line_describes_each_state(state, expect_key, expect_text, expect_color):
    """
    Состояние агента должно читаться с одного взгляда: окно консоли — это
    единственный индикатор того, тратятся ли сейчас токены.
    """
    key, text, color = console_ui.StatusLine()._describe(state)

    assert key == expect_key
    assert expect_text in text
    assert color == expect_color, "цвет не соответствует состоянию"


def test_running_line_shows_pid_and_uptime():
    _, text, _ = console_ui.StatusLine()._describe(
        {"running": True, "starting": False, "pid": 3788, "uptimeSec": 3725})
    assert "PID 3788" in text
    assert "01:02:05" in text, "время работы разобрано неверно: %s" % text


def test_status_text_survives_the_windows_console_encoding():
    """
    Окно может остаться в cp1251, если chcp не сработал. Символы строки
    состояния обязаны выживать: «?» вместо маркера выглядит как поломка.
    """
    for state in ({"running": False}, {"running": True, "pid": 1, "uptimeSec": 5},
                  {"starting": True}):
        _, text, _ = console_ui.StatusLine()._describe(state)
        assert text.encode("cp1251", errors="replace").decode("cp1251") == text,             "символ не переживает cp1251: %s" % text


def test_colours_are_applied_only_when_enabled(monkeypatch):
    """Без поддержки ANSI escape-коды не должны сыпаться в окно текстом."""
    monkeypatch.setattr(console_ui, "_COLORS_ON", False)
    assert console_ui.paint("текст", console_ui.RED) == "текст"

    monkeypatch.setattr(console_ui, "_COLORS_ON", True)
    painted = console_ui.paint("текст", console_ui.RED)
    assert painted.startswith(console_ui.RED) and painted.endswith(console_ui.RESET)


def test_line_width_counts_visible_characters(capsys, monkeypatch):
    """
    Затирание считается по видимой длине. Если считать по строке с ANSI-кодами,
    остаток предыдущей строки останется на экране.
    """
    monkeypatch.setattr(console_ui, "_COLORS_ON", True)
    line = console_ui.StatusLine()
    line._write("длинная строка состояния", console_ui.GREEN)
    line._write("короткая", console_ui.RED)

    visible = capsys.readouterr().out.split(chr(13))[-1]
    for code in (console_ui.RED, console_ui.GREEN, console_ui.RESET):
        visible = visible.replace(code, "")
    assert visible.rstrip() == "короткая"
    assert len(visible) >= len("длинная строка состояния"), "хвост не затёрт"


def test_batch_prompt_is_explained_only_inside_a_batch_file(monkeypatch, capsys):
    """
    «Terminate batch job (Y/N)?» печатает сам cmd.exe — перевести его нельзя.
    Поясняем заранее, но только когда запущены из .bat: иначе вопроса не будет
    и объяснение собьёт с толку.
    """
    monkeypatch.setattr(console_ui.sys, "platform", "win32")

    monkeypatch.delenv("PROMPT", raising=False)
    console_ui.explain_batch_prompt()
    assert capsys.readouterr().out == "", "объяснение без пакетного файла"

    monkeypatch.setenv("PROMPT", "$P$G")
    console_ui.explain_batch_prompt()
    out = capsys.readouterr().out
    assert "Terminate batch job" in out, "не названо то, что увидит пользователь"
    assert "start.bat" in out and "Агент уже остановлен" in out


def test_status_line_rewrites_itself_without_leftovers(capsys):
    """Короткая строка не должна оставлять хвост от предыдущей, длинной."""
    line = console_ui.StatusLine()
    line._write("Агент: работает · PID 3788 · 00:10:00")
    line._write("Агент: остановлен")

    last = capsys.readouterr().out.split("\r")[-1]
    assert last.startswith("Агент: остановлен")
    assert last.strip() == "Агент: остановлен", "остался хвост прошлой строки"


def test_events_are_printed_on_their_own_lines(capsys):
    line = console_ui.StatusLine()
    line.event("агент запущен (PID 42)")

    text = capsys.readouterr().out
    assert text.endswith("\n"), "событие должно завершаться переводом строки"
    assert "агент запущен (PID 42)" in text

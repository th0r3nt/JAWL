# -*- coding: utf-8 -*-
"""
Чтение журнала: хвост, дозапись, ротация.

Файл пишет другой процесс, поэтому важны не только «прочиталось», но и случаи
на границах: обрезанная строка, недописанная строка, укоротившийся файл.
"""

import io

import pytest

from src.web import logs

REC = "2026-08-25 00:09:41.032 - JAWL.Agent - INFO - [ReAct] Шаг %d.\n"


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    path = tmp_path / "main.log"
    monkeypatch.setattr(logs, "LOG_FILE", path)
    return path


def write(path, text, mode="a"):
    with io.open(path, mode, encoding="utf-8", newline="") as fh:
        fh.write(text)


# ---------------------------------------------------------------- хвост

def test_missing_file_is_not_an_error(log_file):
    assert logs.exists() is False
    assert logs.read_tail() == ("", 0)


def test_tail_returns_whole_small_file(log_file):
    write(log_file, REC % 1 + REC % 2, "w")
    text, offset = logs.read_tail()

    assert text.count("Шаг") == 2
    assert offset == log_file.stat().st_size


def test_tail_drops_the_partial_first_line(log_file):
    """Хвост почти всегда начинается посреди строки — половину записи не отдаём."""
    write(log_file, "".join(REC % i for i in range(200)), "w")

    text, _ = logs.read_tail(max_bytes=200)

    assert text.startswith("2026-"), "первая строка обрезана: %r" % text[:40]
    assert len(text) < 200


def test_tail_keeps_multiline_records_readable(log_file):
    write(log_file, REC % 1 + "[Observation]: мысль\n\nвторой абзац\n" + REC % 2, "w")
    text, _ = logs.read_tail()
    assert "[Observation]: мысль" in text
    assert "второй абзац" in text


# ---------------------------------------------------------------- дозапись

def test_nothing_new_returns_empty(log_file):
    write(log_file, REC % 1, "w")
    _, offset = logs.read_tail()
    assert logs.read_since(offset) == ("", offset)


def test_new_lines_are_returned_once(log_file):
    write(log_file, REC % 1, "w")
    _, offset = logs.read_tail()

    write(log_file, REC % 2 + REC % 3)
    text, new_offset = logs.read_since(offset)

    assert "Шаг 2" in text and "Шаг 3" in text
    assert "Шаг 1" not in text, "старое пришло повторно"
    assert new_offset == log_file.stat().st_size

    assert logs.read_since(new_offset) == ("", new_offset), "то же пришло дважды"


def test_unfinished_line_is_held_back(log_file):
    """
    Строку без перевода дописывают прямо сейчас — отдать её значит показать
    половину записи, а потом вторую половину отдельной строкой.
    """
    write(log_file, REC % 1, "w")
    _, offset = logs.read_tail()

    write(log_file, "2026-08-25 00:10:00.000 - JAWL - INFO - [ReAct] недопи")
    text, new_offset = logs.read_since(offset)

    assert text == "", "отдана недописанная строка"
    assert new_offset == offset, "смещение сдвинулось за незавершённую строку"

    write(log_file, "санная строка.\n")
    text, _ = logs.read_since(offset)
    assert "недописанная строка" in text


def test_multiline_record_arrives_whole(log_file):
    write(log_file, REC % 1, "w")
    _, offset = logs.read_tail()

    write(log_file, "2026-08-25 00:11:00.000 - JAWL.Agent - INFO - [Thoughts]:\n"
                    "[Observation]: первая часть\n\n[Reasoning]: вторая часть\n")
    text, _ = logs.read_since(offset)

    assert "[Thoughts]:" in text
    assert "[Reasoning]: вторая часть" in text


# ---------------------------------------------------------------- ротация

def test_rotation_restarts_from_the_beginning(log_file):
    """
    Фреймворк ротирует журнал по max_file_size_mb. После ротации файл короче
    прежнего смещения — читать надо сначала, иначе поток замолчит навсегда.
    """
    write(log_file, "".join(REC % i for i in range(50)), "w")
    _, offset = logs.read_tail()

    write(log_file, REC % 99, "w")            # файл перезаписан с нуля
    text, new_offset = logs.read_since(offset)

    assert "Шаг 99" in text
    assert new_offset == log_file.stat().st_size


def test_chunk_size_is_capped(log_file, monkeypatch):
    """Огромный прирост не должен уехать в поток одним куском."""
    monkeypatch.setattr(logs, "CHUNK_LIMIT", 200)
    write(log_file, REC % 1, "w")
    _, offset = logs.read_tail()

    write(log_file, "".join(REC % i for i in range(100)))
    text, new_offset = logs.read_since(offset)

    assert 0 < len(text.encode("utf-8")) <= 200
    assert new_offset < log_file.stat().st_size, "прочитано больше лимита"

    text2, _ = logs.read_since(new_offset)
    assert text2, "остаток не отдаётся следующим чтением"

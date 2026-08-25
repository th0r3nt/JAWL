# -*- coding: utf-8 -*-
"""
Чтение журнала фреймворка для консоли.

Файл пишется другим процессом и может быть перезаписан ротацией
(`system.logging.max_file_size_mb` и `backup_count`), поэтому:

* читаем по смещению в байтах, а не по строкам;
* если файл вдруг стал короче — это ротация, начинаем сначала;
* отдаём только целые строки, обрезок последней строки придерживаем до
  следующего чтения, иначе клиент получит половину записи.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from src.web import config_io as cio

LOG_FILE = cio.ROOT_DIR / "logs" / "main.log"

TAIL_BYTES = 256 * 1024      # столько хвоста отдаём при открытии вкладки
CHUNK_LIMIT = 512 * 1024     # больше за раз не шлём, чтобы не забить поток


def exists() -> bool:
    return LOG_FILE.exists()


def size() -> int:
    try:
        return LOG_FILE.stat().st_size
    except OSError:
        return 0


def read_tail(max_bytes: int = TAIL_BYTES) -> Tuple[str, int]:
    """
    Хвост журнала и смещение, с которого продолжать чтение.

    Первая строка отбрасывается, если хвост начался не с начала файла: она
    почти наверняка обрезана посередине.
    """
    if not LOG_FILE.exists():
        return "", 0

    total = size()
    start = max(0, total - max_bytes)
    try:
        with open(LOG_FILE, "rb") as fh:
            fh.seek(start)
            raw = fh.read()
    except OSError:
        return "", total

    text = raw.decode("utf-8", errors="replace")
    if start > 0:
        cut = text.find("\n")
        text = text[cut + 1:] if cut >= 0 else ""
    return text, total


def read_since(offset: int) -> Tuple[str, int]:
    """
    Новое, что появилось в файле после `offset`.

    Возвращает текст (только целые строки) и новое смещение. Хвост без
    перевода строки остаётся в файле «непрочитанным» — придёт следующим разом.
    """
    total = size()

    if total < offset:                     # файл укоротился — сработала ротация
        offset = 0
    if total == offset:
        return "", offset

    try:
        with open(LOG_FILE, "rb") as fh:
            fh.seek(offset)
            raw = fh.read(CHUNK_LIMIT)
    except OSError:
        return "", offset

    if not raw:
        return "", offset

    cut = raw.rfind(b"\n")
    if cut < 0:
        return "", offset                  # целой строки пока нет
    complete, raw = raw[:cut + 1], None

    return complete.decode("utf-8", errors="replace"), offset + cut + 1

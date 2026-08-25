# -*- coding: utf-8 -*-
"""
То, что видно в окне терминала, пока работает консоль.

Задача простая: у агента нет своего окна, и без индикатора непонятно, работает
он сейчас или нет — а работающий агент тратит токены. Поэтому окно консоли само
становится этим индикатором:

* нижняя строка обновляется на месте и показывает текущее состояние;
* смены состояния печатаются отдельными строками со временем — остаётся история;
* при закрытии окна агент останавливается, но только если его запускала консоль.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from typing import Optional

from src.web import agent

REFRESH_SEC = 2.0
CLOSE_TIMEOUT_SEC = 4        # Windows даёт около пяти секунд на реакцию

# Цвета теми же сырыми ANSI-кодами, что и логи фреймворка (src/utils/logger.py).
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
GRAY = "\033[90m"
RESET = "\033[0m"


def enable_colors() -> bool:
    """
    Включает разбор ANSI в окне Windows.

    Классическая консоль по умолчанию печатает escape-последовательности как
    текст. Флаг ENABLE_VIRTUAL_TERMINAL_PROCESSING включает их обработку; если
    не вышло — работаем без цвета, но и без мусора на экране.
    """
    if sys.platform != "win32":
        return bool(getattr(sys.stdout, "isatty", lambda: False)())
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)          # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:                                # noqa: BLE001
        return False


_COLORS_ON = False


def paint(text: str, color: str) -> str:
    return color + text + RESET if _COLORS_ON else text


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _uptime(sec: Optional[int]) -> str:
    if sec is None:
        return ""
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return " · %02d:%02d:%02d" % (h, m, s)


class StatusLine:
    """Строка состояния, которая переписывает саму себя."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._last_state = None
        self._width = 0

        global _COLORS_ON
        _COLORS_ON = enable_colors()

        from src.web import tick

        self._tick = tick.TickWatcher()

    # ---------- вывод ----------

    def _write(self, text: str, color: str = "") -> None:
        """
        Переписывает строку на месте.

        Ширину считаем по видимому тексту: строка с ANSI-кодами длиннее того,
        что занято на экране, и хвост предыдущей строки не стёрся бы.
        """
        pad = max(0, self._width - len(text))
        body = paint(text, color) if color else text
        sys.stdout.write("\r" + body + " " * pad)
        sys.stdout.flush()
        self._width = len(text)

    def event(self, text: str) -> None:
        """Печатает событие отдельной строкой, не затирая её следующим обновлением."""
        self._write("")
        sys.stdout.write("\r%s  %s\n" % (paint(_now(), GRAY), text))
        sys.stdout.flush()
        self._width = 0

    # ---------- цикл ----------

    def _describe(self, state: dict) -> tuple:
        """
        Состояние: ключ, видимый текст строки и её цвет.

        Один лишь pid-файл о готовности не говорит: агент создаёт его на первой
        секунде, а потом минуты поднимает подсистемы — дольше всего качается
        модель эмбеддингов. Поэтому пока журнал не сказал «JAWL started
        successfully», это подъём, а не работа.
        """
        if state.get("stopping"):
            return "stopping", "  • АГЕНТ ОСТАНАВЛИВАЕТСЯ · закрывает базы", YELLOW

        booting = self._boot_step()
        if state.get("starting") or (state.get("running") and booting is not None):
            return ("starting",
                    "  • АГЕНТ ЗАПУСКАЕТСЯ · %s" % (booting or "поднимаются подсистемы"),
                    YELLOW)

        if state.get("running"):
            return ("running",
                    "  • АГЕНТ РАБОТАЕТ · PID %s%s · расходует токены" % (
                        state.get("pid"), _uptime(state.get("uptimeSec"))),
                    GREEN)
        return "stopped", "  • АГЕНТ ОСТАНОВЛЕН · токены не тратятся", RED

    def _boot_step(self):
        """
        Чем занят подъём — по журналу. `None`, если подъём уже закончился.

        Свой разбор, а не общий с вкладкой такта: у того свой курсор в файле, и
        два читателя поделили бы строки между собой.
        """
        try:
            state = self._tick.poll()
        except Exception:                                # noqa: BLE001
            return None
        if state.get("phase") != "starting":
            return None
        return state.get("bootStep") or "поднимаются подсистемы"

    def _loop(self) -> None:
        while not self._stop.wait(REFRESH_SEC):
            try:
                state = agent.status()
            except Exception:                          # noqa: BLE001
                continue
            key, text, color = self._describe(state)

            if self._last_state is not None and key != self._last_state:
                if key == "running":
                    self.event(paint("Агент запущен", GREEN)
                               + " (PID %s)" % state.get("pid"))
                elif key == "stopping":
                    self.event(paint("Агент останавливается", YELLOW))
                elif key == "stopped":
                    self.event(paint("Агент остановлен", RED))
            self._last_state = key
            self._write(text, color)

    def start(self) -> None:
        state = agent.status()
        self._last_state, text, color = self._describe(state)
        self._write(text, color)
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._write("")
        sys.stdout.write("\r")
        sys.stdout.flush()


def shutdown_owned_agent(line: Optional[StatusLine] = None,
                         timeout: int = CLOSE_TIMEOUT_SEC) -> None:
    """
    Гасит агента при выходе — но только того, которого запускала эта консоль.

    Если агент был поднят из CLI до старта консоли, он продолжит работать:
    закрытие окна, открытого «посмотреть настройки», не должно ронять чужой
    процесс.
    """
    if not agent.owns_agent():
        return
    if line:
        line.event("останавливаю агента, которого запускала консоль…")
    else:
        sys.stdout.write("\nОстанавливаю агента…\n")
        sys.stdout.flush()

    result = agent.stop(timeout=timeout)
    message = "агент снят принудительно — не успел завершиться" if result.get("forced") \
        else "агент остановлен"
    if line:
        line.event(message)
    else:
        sys.stdout.write(message + "\n")
        sys.stdout.flush()


def explain_batch_prompt() -> None:
    """
    Поясняет вопрос, который сейчас задаст сама Windows.

    После Ctrl+C в пакетном файле cmd.exe печатает «Terminate batch job (Y/N)?».
    Это его собственное сообщение: перевести или подавить его нельзя — оно
    зашито в командный процессор. Зато можно сказать заранее, что это за вопрос,
    потому что печатается он уже после того, как мы завершились.
    """
    if sys.platform != "win32" or os.environ.get("PROMPT") is None:
        return                      # запущено не из .bat — вопроса не будет

    sys.stdout.write("\n")
    sys.stdout.write(paint(
        "Сейчас Windows спросит: Terminate batch job (Y/N)?\n", YELLOW))
    sys.stdout.write(
        "Это её собственный вопрос «Завершить пакетный файл?» — про start.bat,\n"
        "а не про агента. Агент уже остановлен. Нажмите Y и Enter.\n")
    sys.stdout.flush()


def install_close_handler(callback) -> None:
    """
    Реакция на закрытие окна крестиком.

    Ctrl+C ловится обычным способом, а вот CTRL_CLOSE_EVENT в Python не
    приходит — нужен обработчик консоли Windows. pywin32 уже в зависимостях.
    """
    if sys.platform != "win32":
        return
    try:
        import win32api                               # type: ignore
    except ImportError:
        return

    CTRL_C, CTRL_BREAK = 0, 1

    def handler(ctrl_type):                           # noqa: ANN001
        callback()
        # True означает «событие обработано, дальше не идём». Для закрытия окна
        # это верно: Windows всё равно снимет процесс сразу после обработчика.
        # Для Ctrl+C и Ctrl+Break — нет: вернув True, мы бы подавили штатное
        # завершение, и консоль осталась бы висеть.
        return ctrl_type not in (CTRL_C, CTRL_BREAK)

    try:
        win32api.SetConsoleCtrlHandler(handler, True)
    except Exception:                                 # noqa: BLE001
        pass

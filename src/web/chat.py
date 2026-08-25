# -*- coding: utf-8 -*-
"""
Чат с агентом через его собственный терминальный канал.

У фреймворка уже есть канал оператора — `HostTerminalClient`
(`src/l2_interfaces/host/terminal/client.py`). Это TCP-сервер на случайном
порту, который агент записывает в `terminal.port`; к нему подключается CLI-чат.
Консоль становится вторым таким клиентом, ничего не изобретая:

1. читаем порт из файла;
2. подключаемся и посылаем строку `JAWL_HANDSHAKE` (защита от сканеров портов);
3. шлём `{"text": "..."}` построчно;
4. читаем ответы `{"text": ..., "time": ...}` тем же построчным JSON.

Подключение не бесплатно: первый клиент поднимает событие `HOST_TERMINAL_OPENED`,
последний — `HOST_TERMINAL_CLOSED`, а каждое сообщение публикует
`HOST_TERMINAL_MESSAGE` уровня CRITICAL, то есть будит агента немедленно.
Поэтому держим соединение ровно пока открыта вкладка «Чат», а не всё время
работы консоли: иначе консоль сообщала бы агенту, что оператор смотрит в
терминал, когда никто не смотрит.

История переписки лежит в `history.json` и пишется самим агентом — её видно и
при остановленном агенте.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from src.web import config_io as cio

TERMINAL_DIR = (cio.ROOT_DIR / "src" / "utils" / "local" / "data"
                / "interfaces" / "host" / "terminal")
PORT_FILE = TERMINAL_DIR / "terminal.port"
HISTORY_FILE = TERMINAL_DIR / "history.json"

HANDSHAKE = b"JAWL_HANDSHAKE\n"

CONNECT_TIMEOUT_SEC = 3.0
RETRY_PAUSE_SEC = 2.0
# Перезагрузка страницы рвёт поток на доли секунды. Без задержки агент получал бы
# пару «терминал закрыт» / «терминал открыт» на каждое обновление вкладки.
LINGER_SEC = 5.0

BUFFER_SIZE = 200            # столько последних реплик помним для догоняющих клиентов
MAX_MESSAGE_CHARS = 8000     # длиннее одной строкой протокол не рассчитан принимать


def read_history(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Переписка из файла агента.

    Файл ведёт сам фреймворк, поэтому история видна и при остановленном агенте.
    """
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    rows = []
    for item in data[-limit:]:
        if not isinstance(item, dict):
            continue
        rows.append({
            "sender": str(item.get("sender", "")),
            "text": str(item.get("text", "")),
            "time": str(item.get("time", "")),
        })
    return rows


def agent_port() -> Optional[int]:
    """Порт терминала агента. Файла нет — агент не запущен либо интерфейс выключен."""
    try:
        return int(PORT_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def agent_running() -> bool:
    """Работает ли агент — нужно, чтобы отличить «не запущен» от «запущен без терминала»."""
    try:
        from src.web import agent

        return bool(agent.status().get("running"))
    except Exception:                                    # noqa: BLE001
        return False


def terminal_enabled() -> bool:
    """
    Включён ли интерфейс терминала в `interfaces.yaml`.

    От этого флага зависит весь чат: выключен — агент не поднимает TCP-сервер, и
    разговаривать не через что. Проверяем до попытки подключения, иначе
    пользователь получил бы вместо объяснения отказ сокета.
    """
    try:
        interfaces = cio.load_yaml(cio.INTERFACES_FILE)
        return bool(cio.get_path(interfaces, "host.terminal.enabled", False))
    except Exception:                                    # noqa: BLE001
        return True          # прочитать не смогли — не мешаем попытке подключиться


class ChatBridge:
    """
    Соединение с терминалом агента, живущее, пока открыта вкладка «Чат».

    Держит буфер последних реплик с возрастающими номерами: клиент помнит, что
    он уже показал, и не теряет сообщения между переподключениями.
    """

    def __init__(self) -> None:
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._task: Optional[asyncio.Task] = None
        self._linger: Optional[asyncio.Task] = None

        self._watchers = 0
        self._messages: Deque[Dict[str, Any]] = deque(maxlen=BUFFER_SIZE)
        self._seq = 0
        self._state = "idle"          # idle | connecting | online | offline
        self._error = ""
        self._waiters: List[asyncio.Event] = []

    # ------------------------------------------------------------- состояние

    @property
    def connected(self) -> bool:
        return self._state == "online"

    def status(self) -> Dict[str, Any]:
        return {
            "state": self._state,
            "error": self._error,
            "watchers": self._watchers,
            "seq": self._seq,
            "agentPort": agent_port(),
            # чат целиком зависит от этого флага — интерфейсу нужно знать причину
            "terminalEnabled": terminal_enabled(),
        }

    def since(self, after: int) -> List[Dict[str, Any]]:
        return [m for m in self._messages if m["seq"] > after]

    def _push(self, sender: str, text: str, time_str: str = "") -> Dict[str, Any]:
        self._seq += 1
        message = {
            "seq": self._seq,
            "sender": sender,
            "text": text,
            "time": time_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._messages.append(message)
        self._wake()
        return message

    def _wake(self) -> None:
        """Будит всех, кто ждёт новых сообщений в потоке."""
        for event in self._waiters:
            event.set()

    async def wait_for_change(self, timeout: float) -> None:
        event = asyncio.Event()
        self._waiters.append(event)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            if event in self._waiters:
                self._waiters.remove(event)

    # ------------------------------------------------------------ соединение

    async def acquire(self) -> None:
        """Вкладка «Чат» открыта: поднимаем соединение, если его ещё нет."""
        self._watchers += 1
        if self._linger:
            self._linger.cancel()
            self._linger = None
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def release(self) -> None:
        """
        Вкладка закрыта. Рвём соединение не сразу: перезагрузка страницы иначе
        отправляла бы агенту «терминал закрыт» и тут же «открыт».
        """
        self._watchers = max(0, self._watchers - 1)
        if self._watchers or self._linger:
            return
        self._linger = asyncio.create_task(self._linger_then_close())

    async def _linger_then_close(self) -> None:
        try:
            await asyncio.sleep(LINGER_SEC)
        except asyncio.CancelledError:
            return
        self._linger = None
        if self._watchers == 0:
            await self.close()

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        await self._drop_connection()
        self._state = "idle"
        self._wake()

    async def _drop_connection(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:                                # noqa: BLE001
            pass

    async def _run(self) -> None:
        """Держит соединение: агент может быть ещё не запущен или перезапускаться."""
        try:
            while self._watchers or self._linger:
                # Выключенный интерфейс — не сбой связи, а настройка. Стучаться
                # некуда: сервер терминала агент в этом случае не поднимает.
                if not terminal_enabled():
                    self._set_state("disabled", "")
                    await asyncio.sleep(RETRY_PAUSE_SEC)
                    continue

                port = agent_port()
                if port is None:
                    # Интерфейсы поднимаются при старте агента. Если он работает,
                    # а порта нет — значит, терминал включили уже после запуска,
                    # и настройка подействует только со следующего.
                    self._set_state("offline", "агент запущен без терминала — "
                                    "перезапустите его"
                                    if agent_running() else "агент не запущен")
                    await asyncio.sleep(RETRY_PAUSE_SEC)
                    continue

                try:
                    await self._connect(port)
                except (OSError, asyncio.TimeoutError):
                    # Файл порта остаётся от прошлого запуска, если агента сняли
                    # принудительно. Показывать код ошибки сокета бессмысленно —
                    # причина одна: на том конце никого нет.
                    self._set_state("offline", "агент не отвечает на порту %d" % port)
                    await asyncio.sleep(RETRY_PAUSE_SEC)
                    continue

                try:
                    await self._read_loop()
                finally:
                    await self._drop_connection()
                    if self._state == "online":
                        self._set_state("offline", "соединение закрыто")
                await asyncio.sleep(RETRY_PAUSE_SEC)
        except asyncio.CancelledError:
            raise
        finally:
            await self._drop_connection()

    async def _connect(self, port: int) -> None:
        self._set_state("connecting", "")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port), timeout=CONNECT_TIMEOUT_SEC)

        writer.write(HANDSHAKE)
        await writer.drain()

        self._reader, self._writer = reader, writer
        self._set_state("online", "")

    async def _read_loop(self) -> None:
        assert self._reader is not None
        agent = agent_name()
        while True:
            line = await self._reader.readline()
            if not line:
                return                                   # агент закрыл соединение
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
                body, when = payload.get("text", text), payload.get("time", "")
            except ValueError:
                body, when = text, ""
            if body:
                self._push(agent, body, when)

    # ---------------------------------------------------------------- отправка

    async def send(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "пустое сообщение"}
        if len(text) > MAX_MESSAGE_CHARS:
            return {"ok": False,
                    "error": "слишком длинно: %d символов, предел %d"
                             % (len(text), MAX_MESSAGE_CHARS)}
        # протокол построчный: перевод строки оборвал бы сообщение на середине
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")

        if not terminal_enabled():
            return {"ok": False, "offline": True, "disabled": True,
                    "error": "Интерфейс «Терминал» выключен — отправлять некуда."}

        if not self.connected or self._writer is None:
            return {"ok": False, "offline": True,
                    "error": self._error or "нет связи с терминалом агента"}

        payload = json.dumps({"text": text}, ensure_ascii=False) + "\n"
        try:
            self._writer.write(payload.encode("utf-8"))
            await self._writer.drain()
        except Exception as exc:                         # noqa: BLE001
            self._set_state("offline", "не отправилось: %s" % exc)
            return {"ok": False, "offline": True, "error": str(exc)}

        # своё сообщение показываем сразу: агент присылает только свои ответы
        return {"ok": True, "message": self._push("User", text)}

    # ------------------------------------------------------------------ прочее

    def _set_state(self, state: str, error: str) -> None:
        changed = (state != self._state) or (error != self._error)
        self._state, self._error = state, error
        if changed:
            self._wake()


def agent_name() -> str:
    """Имя агента из настроек — им подписаны его реплики."""
    try:
        settings = cio.load_yaml(cio.SETTINGS_FILE)
        return str(cio.get_path(settings, "identity.agent_name") or "Агент")
    except Exception:                                    # noqa: BLE001
        return "Агент"


_bridge: Optional[ChatBridge] = None


def bridge() -> ChatBridge:
    """Один мост на процесс: соединение и буфер должны переживать запросы."""
    global _bridge
    if _bridge is None:
        _bridge = ChatBridge()
    return _bridge

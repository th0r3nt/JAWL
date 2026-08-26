# -*- coding: utf-8 -*-
"""
Чат с агентом через его терминальный канал.

Разговор идёт не по выдуманному протоколу, а по тому, который агент уже
обслуживает сам (`src/l2_interfaces/host/terminal/client.py`): рукопожатие
строкой `JAWL_HANDSHAKE`, дальше построчный JSON в обе стороны.

Тесты поднимают поддельный терминальный сервер, повторяющий этот протокол.
Настоящего агента они не запускают: подключение к нему — это событие
`HOST_TERMINAL_OPENED`, а сообщение — `HOST_TERMINAL_MESSAGE` уровня CRITICAL,
то есть немедленное пробуждение и расход токенов.
"""

import asyncio
import json

import pytest

from src.web import chat


class FakeTerminal:
    """Терминальный сервер агента: то же рукопожатие и то же построчное JSON."""

    def __init__(self):
        self.received = []
        self.handshakes = []
        self.connections = 0
        self.disconnections = 0
        self._writers = set()
        self._server = None
        self.port = 0

    async def start(self):
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        for writer in list(self._writers):
            writer.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader, writer):
        handshake = (await reader.readline()).decode().strip()
        self.handshakes.append(handshake)
        if handshake != "JAWL_HANDSHAKE":
            writer.close()                   # так агент отшивает сканеры портов
            return

        self.connections += 1
        self._writers.add(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                self.received.append(json.loads(line.decode()))
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            self._writers.discard(writer)
            self.disconnections += 1

    async def say(self, text, time_str="2026-08-25 12:00:00"):
        """Реплика агента всем подключённым терминалам."""
        payload = json.dumps({"text": text, "time": time_str}, ensure_ascii=False) + "\n"
        for writer in list(self._writers):
            writer.write(payload.encode("utf-8"))
            await writer.drain()


@pytest.fixture
async def terminal(tmp_path, monkeypatch):
    """Поддельный терминал агента и подменённые пути к его файлам."""
    monkeypatch.setattr(chat, "TERMINAL_DIR", tmp_path)
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "terminal.port")
    monkeypatch.setattr(chat, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(chat, "RETRY_PAUSE_SEC", 0.05)
    monkeypatch.setattr(chat, "LINGER_SEC", 0.05)
    # интерфейс терминала задаём явно: в рабочем конфиге он может быть выключен,
    # и тогда мост откажется подключаться — это отдельный набор тестов ниже
    monkeypatch.setattr(chat, "terminal_enabled", lambda: True)

    server = FakeTerminal()
    await server.start()
    (tmp_path / "terminal.port").write_text(str(server.port), encoding="utf-8")

    yield server
    await server.stop()


async def until(check, timeout=3.0):
    """Ждёт условия — соединение поднимается в фоне, а не синхронно."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if check():
            return True
        await asyncio.sleep(0.02)
    return False


# ---------------------------------------------------------------- история

def test_history_is_read_from_the_agents_file(tmp_path, monkeypatch):
    """
    Файл ведёт сам агент, поэтому переписка видна и при остановленном агенте —
    иначе вкладка выглядела бы пустой каждый раз после перезапуска.
    """
    path = tmp_path / "history.json"
    path.write_text(json.dumps([
        {"time": "2026-08-25 12:00:00", "sender": "User", "text": "привет"},
        {"time": "2026-08-25 12:00:05", "sender": "Tess", "text": "привет!"},
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(chat, "HISTORY_FILE", path)

    rows = chat.read_history()

    assert [r["sender"] for r in rows] == ["User", "Tess"]
    assert rows[1]["text"] == "привет!"


def test_history_limit_keeps_the_newest(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    path.write_text(json.dumps(
        [{"time": "t", "sender": "User", "text": str(i)} for i in range(100)]),
        encoding="utf-8")
    monkeypatch.setattr(chat, "HISTORY_FILE", path)

    rows = chat.read_history(limit=10)

    assert len(rows) == 10 and rows[-1]["text"] == "99"


@pytest.mark.parametrize("content", ["не json", "{}", "[1, 2, 3]", ""])
def test_broken_history_does_not_break_the_tab(tmp_path, monkeypatch, content):
    path = tmp_path / "history.json"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(chat, "HISTORY_FILE", path)

    assert chat.read_history() == []


def test_missing_history_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "HISTORY_FILE", tmp_path / "нет.json")
    assert chat.read_history() == []


# ---------------------------------------------------------------- порт

def test_port_is_read_from_the_agents_file(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "terminal.port")
    (tmp_path / "terminal.port").write_text("54321\n", encoding="utf-8")

    assert chat.agent_port() == 54321


@pytest.mark.parametrize("content", ["", "не число", "  "])
def test_broken_port_file_reads_as_absent(tmp_path, monkeypatch, content):
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "terminal.port")
    (tmp_path / "terminal.port").write_text(content, encoding="utf-8")

    assert chat.agent_port() is None


def test_missing_port_file_means_agent_is_down(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "нет.port")
    assert chat.agent_port() is None


# ---------------------------------------------------------------- соединение

async def test_handshake_matches_the_framework(terminal):
    """
    Без правильного рукопожатия агент молча рвёт соединение — так он отшивает
    сканеры портов. Строка должна совпадать дословно.
    """
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected), "не подключились"
        assert terminal.handshakes == ["JAWL_HANDSHAKE"]
    finally:
        await link.close()


async def test_agent_replies_reach_the_buffer(terminal):
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)
        await terminal.say("готово")

        assert await until(lambda: len(link.since(0)) == 1)
        message = link.since(0)[0]
        assert message["text"] == "готово"
        assert message["time"] == "2026-08-25 12:00:00", "время агента заменено своим"
        assert message["sender"] != "User"
    finally:
        await link.close()


async def test_messages_get_growing_numbers(terminal):
    """Клиент помнит, что уже показал: номера не должны повторяться."""
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)
        await terminal.say("раз")
        await terminal.say("два")
        assert await until(lambda: len(link.since(0)) == 2)

        seqs = [m["seq"] for m in link.since(0)]
        assert seqs == sorted(seqs) and len(set(seqs)) == 2
        assert link.since(seqs[0]) == link.since(0)[1:], "выборка «после N» неверна"
    finally:
        await link.close()


async def test_offline_when_the_agent_is_not_running(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "нет.port")
    monkeypatch.setattr(chat, "RETRY_PAUSE_SEC", 0.05)
    monkeypatch.setattr(chat, "terminal_enabled", lambda: True)
    # состояние настоящей машины сюда попадать не должно: если на компьютере
    # окажется живой агент, ответ будет другим, и тест начнёт «мигать»
    monkeypatch.setattr(chat, "agent_running", lambda: False)

    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.status()["state"] == "offline")
        assert not link.connected
        assert "не запущен" in link.status()["error"]
    finally:
        await link.close()


async def test_reconnects_after_the_agent_restarts(terminal):
    """Агента перезапускают — вкладка не должна требовать перезагрузки страницы."""
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)

        await terminal.stop()                # агент ушёл
        assert await until(lambda: not link.connected)

        await terminal.start()               # и вернулся на другом порту
        chat.PORT_FILE.write_text(str(terminal.port), encoding="utf-8")

        assert await until(lambda: link.connected, timeout=5.0), "не переподключились"
    finally:
        await link.close()


# ---------------------------------------------------------------- отправка

async def test_message_reaches_the_agent(terminal):
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)
        res = await link.send("проверка связи")

        assert res["ok"] is True
        assert await until(lambda: len(terminal.received) == 1)
        assert terminal.received[0] == {"text": "проверка связи"}
    finally:
        await link.close()


async def test_own_message_appears_immediately(terminal):
    """Агент присылает только свои реплики — своё сообщение показываем сами."""
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)
        res = await link.send("привет")

        assert res["message"]["sender"] == "User"
        assert link.since(0)[-1]["text"] == "привет"
    finally:
        await link.close()


async def test_newlines_are_flattened(terminal):
    """
    Протокол построчный: перевод строки внутри сообщения оборвал бы его на
    середине, и агент получил бы половину.
    """
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)
        await link.send("первая\nвторая\r\nтретья")

        assert await until(lambda: len(terminal.received) == 1)
        assert "\n" not in terminal.received[0]["text"]
        assert terminal.received[0]["text"] == "первая вторая третья"
    finally:
        await link.close()


async def test_sending_without_connection_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "нет.port")

    link = chat.ChatBridge()
    res = await link.send("никуда")

    assert res["ok"] is False and res["offline"] is True


@pytest.mark.parametrize("text", ["", "   ", "\n"])
async def test_empty_messages_are_refused(terminal, text):
    """Пустое сообщение разбудило бы агента без причины."""
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)
        res = await link.send(text)

        assert res["ok"] is False
        assert terminal.received == []
    finally:
        await link.close()


async def test_too_long_message_is_refused(terminal):
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)
        res = await link.send("я" * (chat.MAX_MESSAGE_CHARS + 1))

        assert res["ok"] is False and "слишком длинно" in res["error"]
        assert terminal.received == []
    finally:
        await link.close()


# ------------------------------------------------- присутствие оператора

async def test_connection_is_held_only_while_watched(terminal):
    """
    Открытое соединение агент видит как «оператор смотрит в терминал»
    (HOST_TERMINAL_OPENED / CLOSED). Держать его без открытой вкладки значило бы
    вводить агента в заблуждение.
    """
    link = chat.ChatBridge()
    await link.acquire()
    assert await until(lambda: link.connected)

    await link.release()
    assert await until(lambda: not link.connected, timeout=2.0), "соединение не закрылось"
    assert terminal.disconnections >= 1


async def test_reload_does_not_flap_the_connection(terminal):
    """
    Перезагрузка страницы рвёт поток на доли секунды. Без задержки агент получал
    бы «терминал закрыт» и тут же «открыт» на каждое обновление вкладки.
    """
    link = chat.ChatBridge()
    await link.acquire()
    assert await until(lambda: link.connected)

    await link.release()                     # вкладка закрылась…
    await link.acquire()                     # …и сразу открылась снова
    await asyncio.sleep(chat.LINGER_SEC * 3)

    try:
        assert link.connected, "соединение всё-таки оборвалось"
        assert terminal.connections == 1, "агент увидел лишнее переподключение"
    finally:
        await link.close()


async def test_second_watcher_does_not_reconnect(terminal):
    """Две открытые вкладки — одно соединение, а не два «оператора»."""
    link = chat.ChatBridge()
    await link.acquire()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)
        await asyncio.sleep(0.1)
        assert terminal.connections == 1
    finally:
        await link.close()


# ---------------------------------------------------------------- ожидание

async def test_waiters_are_woken_by_a_message(terminal):
    """Поток ждёт события, а не опрашивает буфер: иначе реплика приходит с лагом."""
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.connected)

        waiter = asyncio.create_task(link.wait_for_change(timeout=3.0))
        await asyncio.sleep(0.05)
        await terminal.say("эй")

        await asyncio.wait_for(waiter, timeout=2.0)
    finally:
        await link.close()


def test_agent_name_comes_from_settings(monkeypatch):
    """Реплики агента подписаны его именем из настроек, а не «Агент»."""
    from src.web import config_io as cio

    monkeypatch.setattr(cio, "load_yaml", lambda _p: {"identity": {"agent_name": "Тесс"}})
    assert chat.agent_name() == "Тесс"


def test_agent_name_falls_back(monkeypatch):
    from src.web import config_io as cio

    monkeypatch.setattr(cio, "load_yaml", lambda _p: {})
    assert chat.agent_name() == "Агент"


# ------------------------------------------------- выключенный интерфейс

@pytest.fixture
def terminal_off(monkeypatch):
    monkeypatch.setattr(chat, "terminal_enabled", lambda: False)
    monkeypatch.setattr(chat, "RETRY_PAUSE_SEC", 0.05)


def test_enabled_flag_is_read_from_interfaces(monkeypatch):
    """Весь чат зависит от этого флага — читать его надо из конфигурации."""
    from src.web import config_io as cio

    monkeypatch.setattr(cio, "load_yaml",
                        lambda _p: {"host": {"terminal": {"enabled": True}}})
    assert chat.terminal_enabled() is True

    monkeypatch.setattr(cio, "load_yaml",
                        lambda _p: {"host": {"terminal": {"enabled": False}}})
    assert chat.terminal_enabled() is False


def test_unreadable_config_does_not_block_the_chat(monkeypatch):
    """Не смогли прочитать конфиг — не выдумываем запрет, пробуем подключиться."""
    from src.web import config_io as cio

    def boom(_path):
        raise OSError("нет файла")

    monkeypatch.setattr(cio, "load_yaml", boom)
    assert chat.terminal_enabled() is True


async def test_disabled_terminal_is_not_a_connection_failure(terminal, terminal_off):
    """
    Выключенный интерфейс — это настройка, а не сбой. Сообщать о нём отказом
    сокета значит прятать причину: пользователь видел бы «[WinError 1225]»
    вместо «включите терминал».
    """
    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.status()["state"] == "disabled")
        assert link.status()["terminalEnabled"] is False
        assert not link.status()["error"], "у настройки не должно быть текста ошибки"
        assert terminal.connections == 0, "стучались в терминал, которого нет"
    finally:
        await link.close()


async def test_sending_with_disabled_terminal_explains_why(terminal_off):
    link = chat.ChatBridge()
    res = await link.send("привет")

    assert res["ok"] is False
    assert res["disabled"] is True
    assert "Терминал" in res["error"], "причина не названа"


async def test_stale_port_file_reads_as_agent_not_answering(tmp_path, monkeypatch):
    """
    Файл порта остаётся от прошлого запуска, если агента сняли принудительно.
    Пользователю нужна причина, а не код ошибки сокета.
    """
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "terminal.port")
    monkeypatch.setattr(chat, "terminal_enabled", lambda: True)
    monkeypatch.setattr(chat, "RETRY_PAUSE_SEC", 0.05)

    # порт, на котором заведомо никто не слушает
    (tmp_path / "terminal.port").write_text("1", encoding="utf-8")

    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.status()["state"] == "offline")
        error = link.status()["error"]
        assert "не отвечает" in error, "непонятная причина: %s" % error
        assert "WinError" not in error, "наружу торчит код ошибки сокета"
        assert "Errno" not in error
    finally:
        await link.close()


@pytest.mark.parametrize("running, expected", [
    (False, "агент не запущен"),
    (True, "агент запущен без терминала — перезапустите его"),
])
async def test_missing_port_file_explains_the_reason(tmp_path, monkeypatch,
                                                     running, expected):
    """
    Порта нет по двум разным причинам, и подсказки нужны разные: интерфейсы
    поднимаются при старте, поэтому включённый уже после запуска терминал
    заработает только со следующего.
    """
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "нет.port")
    monkeypatch.setattr(chat, "terminal_enabled", lambda: True)
    monkeypatch.setattr(chat, "RETRY_PAUSE_SEC", 0.05)
    monkeypatch.setattr(chat, "agent_running", lambda: running)

    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.status()["state"] == "offline")
        assert link.status()["error"] == expected
    finally:
        await link.close()


async def test_status_always_carries_the_flag(terminal_off):
    """Интерфейсу нужен флаг и до первой попытки подключения."""
    assert chat.ChatBridge().status()["terminalEnabled"] is False


async def test_enabled_after_start_asks_for_a_restart(tmp_path, monkeypatch):
    """
    Самый сбивающий с толку случай: терминал включили в настройках, а агент уже
    работает без него. Интерфейсы поднимаются при старте, так что настройка
    подействует только со следующего запуска — об этом надо сказать.
    """
    monkeypatch.setattr(chat, "PORT_FILE", tmp_path / "нет.port")
    monkeypatch.setattr(chat, "terminal_enabled", lambda: True)
    monkeypatch.setattr(chat, "agent_running", lambda: True)
    monkeypatch.setattr(chat, "RETRY_PAUSE_SEC", 0.05)

    link = chat.ChatBridge()
    await link.acquire()
    try:
        assert await until(lambda: link.status()["state"] == "offline")
        assert "перезапустите" in link.status()["error"], \
            "не сказано, что нужен перезапуск: %s" % link.status()["error"]
    finally:
        await link.close()


def test_agent_running_check_survives_a_broken_status(monkeypatch):
    """Проверка состояния агента не должна ронять чат, если сама не сработала."""
    from src.web import agent

    def boom():
        raise RuntimeError("нет доступа")

    monkeypatch.setattr(agent, "status", boom)
    assert chat.agent_running() is False

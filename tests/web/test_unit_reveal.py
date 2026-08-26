# -*- coding: utf-8 -*-
"""
Кнопка «Открыть»: какую папку показать и какой командой.

Команда строится отдельной функцией, чтобы проверять её, не открывая окон
файлового менеджера.
"""

import pytest

from src.web import config_io as cio
from src.web import server


ROOT = cio.ROOT_DIR


# ---------------------------------------------------------------- выбор папки

def test_directory_opens_itself():
    select, folder, err = server.resolve_target("config")
    assert err is None
    assert select is None
    assert folder == ROOT / "config"


def test_existing_file_opens_its_folder_and_gets_selected():
    """
    Берём файл, который лежит в репозитории. `settings.yaml` для этого не
    годится: он в `.gitignore` и в свежем клоне отсутствует — тест проверял бы
    тогда не подсветку файла, а откат к ближайшей папке.
    """
    select, folder, err = server.resolve_target("config/settings.example.yaml")
    assert err is None
    assert select == ROOT / "config" / "settings.example.yaml"
    assert folder == ROOT / "config"


def test_missing_file_falls_back_to_nearest_existing_folder():
    """
    Часть файлов на вкладке «Исходные файлы» может ещё не существовать. Кнопка
    обещает показать папку — значит «не найдено» здесь неуместно, надо открыть
    ближайший существующий каталог.

    Файл берём заведомо отсутствующий: SOUL.md и EXAMPLES_OF_STYLE.md для этого
    больше не годятся — консоль создаёт их при запуске, и тест проверял бы
    подсветку существующего файла вместо отката к папке.
    """
    raw = "src/l3_agent/prompt/personality/НЕТ_ТАКОГО.md"
    select, folder, err = server.resolve_target(raw)
    assert err is None
    assert select is None
    assert folder == ROOT / "src" / "l3_agent" / "prompt" / "personality"


def test_deeply_missing_path_still_lands_inside_project():
    select, folder, err = server.resolve_target("config/nope/deeper/file.yaml")
    assert err is None
    assert folder == ROOT / "config"


@pytest.mark.parametrize("raw", ["../../../Windows", "../..", "/etc/passwd"])
def test_path_outside_project_is_refused(raw):
    """Консоль не должна быть кнопкой «открой что угодно на диске»."""
    _, _, err = server.resolve_target(raw)
    assert err and "вне проекта" in err


# ---------------------------------------------------------------- команда

def test_windows_select_quotes_only_the_path(monkeypatch):
    """
    `explorer /select,<путь>` нельзя передавать списком: subprocess возьмёт в
    кавычки весь аргумент вместе с `/select,`, и explorer молча откроет
    «Документы». В пути к проекту есть пробел — этот тест и ловит регрессию.
    """
    monkeypatch.setattr(server.sys, "platform", "win32")
    target = ROOT / "config" / "settings.yaml"

    command = server.reveal_command(target, target.parent)

    assert isinstance(command, str), "на Windows нужна строка, а не список"
    assert command.startswith('explorer /select,"')
    assert command.endswith('"')
    assert str(target) in command
    assert '"/select' not in command, "кавычка не должна охватывать ключ /select"


def test_windows_folder_is_quoted(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "win32")
    command = server.reveal_command(None, ROOT / "config")
    assert command == 'explorer "%s"' % (ROOT / "config")


@pytest.mark.parametrize("platform, binary", [("darwin", "open"), ("linux", "xdg-open")])
def test_other_platforms_use_a_list(monkeypatch, platform, binary):
    monkeypatch.setattr(server.sys, "platform", platform)
    command = server.reveal_command(None, ROOT / "config")
    assert command == [binary, str(ROOT / "config")]


# ---------------------------------------------------------------- маршрут

async def test_open_endpoint_reports_refusal(sandbox_config):
    from aiohttp.test_utils import TestClient, TestServer

    async with TestClient(TestServer(server.make_app())) as client:
        resp = await client.post("/api/fs/open", json={"path": "../../../Windows"})
        assert resp.status == 400
        body = await resp.json()
        assert body["ok"] is False
        assert "вне проекта" in body["error"]


async def test_open_endpoint_launches_file_manager(sandbox_config, monkeypatch):
    """Проверяем маршрут, но окно не открываем — запуск подменён."""
    from aiohttp.test_utils import TestClient, TestServer

    launched = []
    monkeypatch.setattr(server.subprocess, "Popen",
                        lambda cmd, **kw: launched.append(cmd))

    async with TestClient(TestServer(server.make_app())) as client:
        resp = await client.post("/api/fs/open", json={"path": "config/settings.yaml"})
        assert resp.status == 200
        body = await resp.json()

    assert body["ok"] is True
    assert body["opened"].endswith("config")
    assert len(launched) == 1

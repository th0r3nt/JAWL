# -*- coding: utf-8 -*-
"""
HTTP-сервер веб-консоли.

Взят aiohttp, а не FastAPI: он уже в requirements.txt (используется вебхуками
интерфейса web.hooks), поэтому новых зависимостей консоль не приносит.

По умолчанию слушает только localhost. Консоль управляет агентом, у которого
есть доступ к ОС, — открывать её наружу без обратного прокси и токена нельзя.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from aiohttp import web

from src.web import agent
from src.web import chat as chatsrc
from src.web import config_io as cio
from src.web import database as dbsrc
from src.web import console_ui
from src.web import drives as drivesrc
from src.web import logs as logsrc
from src.web import schema
from src.web import tick as ticksrc

STATIC_DIR = cio.ROOT_DIR / "web"


# ---------------------------------------------------------------- чтение

def read_config() -> Dict[str, Any]:
    settings = cio.load_yaml(cio.SETTINGS_FILE)
    interfaces = cio.load_yaml(cio.INTERFACES_FILE)
    env = cio.load_env()

    values: Dict[str, Any] = {}
    for cfg_key, path in schema.SETTINGS_FIELDS.items():
        values[cfg_key] = cio.get_path(settings, path)
    for cfg_key, path in schema.INTERFACES_FIELDS.items():
        values[cfg_key] = cio.get_path(interfaces, path)
    for cfg_key, env_key in schema.ENV_FIELDS.items():
        values[cfg_key] = env.get(env_key, "")

    lists: Dict[str, Any] = {}
    for list_id, path in schema.SETTINGS_LISTS.items():
        lists[list_id] = [str(x) for x in (cio.get_path(settings, path) or [])]
    for list_id, path in schema.INTERFACES_LISTS.items():
        lists[list_id] = [str(x) for x in (cio.get_path(interfaces, path) or [])]
    for list_id, (path, keys) in schema.INTERFACES_OBJECT_LISTS.items():
        lists[list_id] = [
            {k: str(row.get(k, "")) for k in keys}
            for row in (cio.get_path(interfaces, path) or [])
        ]
    for list_id, prefix in schema.ENV_LISTS.items():
        lists[list_id] = cio.env_prefixed(prefix)

    return {
        "ok": True,
        "values": values,
        "lists": lists,
        # версия фреймворка, а не консоли: рядом с надписью JAWL в углу
        "version": cio.framework_version(),
    }


# ---------------------------------------------------------------- запись

def write_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    values = payload.get("values") or {}
    lists = payload.get("lists") or {}

    unknown = []
    touched_env = False

    scalars: Dict[str, Any] = {}
    ifc_scalars: Dict[str, Any] = {}
    for cfg_key, value in values.items():
        if cfg_key in schema.SETTINGS_FIELDS:
            scalars[schema.SETTINGS_FIELDS[cfg_key]] = value
        elif cfg_key in schema.INTERFACES_FIELDS:
            ifc_scalars[schema.INTERFACES_FIELDS[cfg_key]] = value
        elif cfg_key not in schema.ENV_FIELDS:
            unknown.append(cfg_key)

    def _clean(items):
        return [str(x).strip() for x in items if str(x).strip()]

    yaml_lists, ifc_lists, ifc_objects = {}, {}, {}
    for list_id, items in lists.items():
        if list_id in schema.SETTINGS_LISTS:
            yaml_lists[schema.SETTINGS_LISTS[list_id]] = _clean(items)
        elif list_id in schema.INTERFACES_LISTS:
            ifc_lists[schema.INTERFACES_LISTS[list_id]] = _clean(items)
        elif list_id in schema.INTERFACES_OBJECT_LISTS:
            path, keys = schema.INTERFACES_OBJECT_LISTS[list_id]
            rows = [r for r in items if isinstance(r, dict) and any(str(r.get(k, "")).strip() for k in keys)]
            ifc_objects[path] = (rows, keys)

    touched_settings = bool(scalars or yaml_lists)
    if touched_settings:
        missing = cio.apply_yaml(cio.SETTINGS_FILE, scalars, yaml_lists)
        unknown.extend(missing)
        touched_settings = len(scalars) + len(yaml_lists) > len(missing)

    touched_interfaces = bool(ifc_scalars or ifc_lists or ifc_objects)
    if touched_interfaces:
        missing = cio.apply_yaml(cio.INTERFACES_FILE, ifc_scalars, ifc_lists, ifc_objects)
        unknown.extend(missing)
        touched_interfaces = len(ifc_scalars) + len(ifc_lists) + len(ifc_objects) > len(missing)

    env_values = {
        schema.ENV_FIELDS[k]: ("" if v is None else str(v))
        for k, v in values.items() if k in schema.ENV_FIELDS
    }
    env_prefixed = {}
    for list_id, prefix in schema.ENV_LISTS.items():
        if list_id in lists:
            env_prefixed[prefix] = [str(x).strip() for x in lists[list_id] if str(x).strip()]

    if env_values or env_prefixed:
        cio.save_env(env_values, env_prefixed)
        touched_env = True

    written = []
    if touched_settings:
        written.append("config/settings.yaml")
    if touched_interfaces:
        written.append("config/interfaces.yaml")
    if touched_env:
        written.append(".env")

    return {
        "ok": True,
        "written": written,
        "unknown": unknown,
        # TODO: пройти по параметрам и отметить те, что не перечитываются на ходу
        "restartRequired": [],
    }


# ---------------------------------------------------------------- файловый менеджер

def resolve_target(raw: str) -> Tuple[Optional[Path], Optional[Path], Optional[str]]:
    """
    Разбирает запрошенный путь в пару (что подсветить, какую папку открыть).

    Файла может ещё не быть: SOUL.md и EXAMPLES_OF_STYLE.md появляются только
    при первом запуске агента, в репозитории лежат лишь .example-заготовки.
    Кнопка обещает показать папку — значит, поднимаемся до ближайшего
    существующего каталога, а не отвечаем «не найдено».

    Возвращает (файл_для_подсветки, папка, ошибка).
    """
    target = (cio.ROOT_DIR / raw).resolve()
    try:
        target.relative_to(cio.ROOT_DIR)
    except ValueError:
        return None, None, "путь вне проекта: %s" % raw

    if target.is_dir():
        return None, target, None
    if target.exists():
        return target, target.parent, None

    folder = target.parent
    while not folder.exists() and folder != cio.ROOT_DIR:
        folder = folder.parent
    if not folder.exists():
        return None, None, "не найдено: %s" % raw
    return None, folder, None


def reveal_command(select: Optional[Path], folder: Path):
    """
    Команда запуска файлового менеджера.

    Вынесена отдельно, чтобы её можно было проверить тестом, не открывая окон.

    Тонкость Windows: `explorer /select,<путь>` нельзя передавать списком —
    subprocess возьмёт в кавычки весь аргумент вместе с `/select,`, explorer
    такое не разберёт и молча откроет «Документы». Нужна строка, где в кавычках
    только путь.
    """
    if sys.platform == "win32":
        if select is not None:
            return 'explorer /select,"%s"' % select
        return 'explorer "%s"' % folder
    if sys.platform == "darwin":
        return ["open", str(folder)]
    return ["xdg-open", str(folder)]


def reveal_path(raw: str) -> Dict[str, Any]:
    """Открывает каталог запрошенного пути в файловом менеджере ОС."""
    select, folder, error = resolve_target(raw)
    if error:
        return {"ok": False, "error": error}

    command = reveal_command(select, folder)
    try:
        # строка вместо списка — только на Windows и осознанно, см. reveal_command
        subprocess.Popen(command, shell=isinstance(command, str))
    except Exception as exc:                           # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "opened": str(folder)}


# ---------------------------------------------------------------- маршруты

def make_app(token: str | None = None) -> web.Application:
    app = web.Application()

    # разбор такта продвигает смещение в журнале: два одновременных запроса
    # поделили бы между собой один пакет строк и разошлись бы в состоянии
    tick_lock = asyncio.Lock()

    @web.middleware
    async def guard(request: web.Request, handler):
        if token and request.path.startswith("/api/"):
            given = request.headers.get("X-Console-Token") or request.query.get("token")
            if given != token:
                return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        return await handler(request)

    app.middlewares.append(guard)

    async def get_config(_request: web.Request) -> web.Response:
        try:
            return web.json_response(read_config())
        except FileNotFoundError as exc:
            return web.json_response({"ok": False, "error": "нет файла: %s" % exc}, status=500)

    async def put_config(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "ожидался JSON"}, status=400)
        try:
            return web.json_response(write_config(payload))
        except Exception as exc:                       # noqa: BLE001 — наружу текстом
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    async def index(_request: web.Request) -> web.Response:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def post_open(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "ожидался JSON"}, status=400)
        result = reveal_path(str(payload.get("path") or ""))
        return web.json_response(result, status=200 if result["ok"] else 400)

    async def agent_status(_request: web.Request) -> web.Response:
        return web.json_response(await asyncio.to_thread(agent.status))

    async def agent_start(_request: web.Request) -> web.Response:
        # запуск ждёт несколько секунд — уводим в поток, чтобы не блокировать сервер
        result = await asyncio.to_thread(agent.start)
        return web.json_response(result, status=200 if result["ok"] else 409)

    async def agent_stop(_request: web.Request) -> web.Response:
        result = await asyncio.to_thread(agent.stop)
        return web.json_response(result, status=200 if result["ok"] else 409)

    async def logs_tail(request: web.Request) -> web.Response:
        if not logsrc.exists():
            return web.json_response({"ok": True, "text": "", "offset": 0,
                                      "missing": True})
        text, offset = await asyncio.to_thread(logsrc.read_tail)
        return web.json_response({"ok": True, "text": text, "offset": offset})

    async def logs_stream(request: web.Request) -> web.StreamResponse:
        """Дозапись журнала через Server-Sent Events."""
        resp = web.StreamResponse(headers={
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",      # чтобы обратный прокси не буферизовал
        })
        await resp.prepare(request)

        try:
            offset = int(request.query.get("offset", "0"))
        except ValueError:
            offset = 0

        idle = 0
        try:
            while True:
                await asyncio.sleep(1.0)
                text, offset = await asyncio.to_thread(logsrc.read_since, offset)
                if text:
                    idle = 0
                    payload = json.dumps({"text": text, "offset": offset},
                                         ensure_ascii=False)
                    await resp.write(("data: %s\n\n" % payload).encode("utf-8"))
                else:
                    idle += 1
                    if idle >= 15:          # держим соединение живым
                        idle = 0
                        await resp.write(b": ping\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass                            # вкладку закрыли — это нормально
        except Exception:                   # noqa: BLE001
            pass
        return resp

    async def logs_download(_request: web.Request) -> web.StreamResponse:
        if not logsrc.exists():
            return web.json_response({"ok": False, "error": "файл журнала не найден"},
                                     status=404)
        return web.FileResponse(logsrc.LOG_FILE, headers={
            "Content-Disposition": 'attachment; filename="main.log"',
        })

    async def tick_state(_request: web.Request) -> web.Response:
        """
        Состояние такта для шапки: фаза, шаг ReAct, время до пробуждения.

        Разбор журнала держит смещение между запросами, поэтому обработчик
        обязан быть последовательным — за это отвечает `tick_lock`.
        """
        async with tick_lock:
            return web.json_response(await asyncio.to_thread(ticksrc.state))

    async def chat_history(_request: web.Request) -> web.Response:
        """
        Переписка и состояние связи.

        История лежит в файле агента, поэтому видна и при остановленном агенте —
        а состояние связи говорит, можно ли сейчас писать.
        """
        rows = await asyncio.to_thread(chatsrc.read_history)
        return web.json_response({
            "ok": True,
            "history": rows,
            "agentName": await asyncio.to_thread(chatsrc.agent_name),
            "status": chatsrc.bridge().status(),
        })

    async def chat_send(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "ожидался JSON"}, status=400)

        result = await chatsrc.bridge().send((payload or {}).get("text", ""))
        if result["ok"]:
            return web.json_response(result)
        return web.json_response(result, status=409 if result.get("offline") else 400)

    async def chat_stream(request: web.Request) -> web.StreamResponse:
        """
        Поток реплик агента.

        Пока держится этот поток, консоль считается открытым терминалом
        оператора: соединение с агентом поднимается на время подписки и
        закрывается, когда вкладку покинули. Событиями OPENED/CLOSED это видит и
        сам агент, поэтому врать ему о присутствии оператора не стоит.
        """
        resp = web.StreamResponse(headers={
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })
        await resp.prepare(request)

        try:
            after = int(request.query.get("after", "0"))
        except ValueError:
            after = 0

        link = chatsrc.bridge()
        await link.acquire()
        last_status = None
        try:
            while True:
                fresh = link.since(after)
                status = link.status()
                if fresh or status != last_status:
                    if fresh:
                        after = fresh[-1]["seq"]
                    last_status = status
                    body = json.dumps({"messages": fresh, "status": status},
                                      ensure_ascii=False)
                    await resp.write(("data: %s\n\n" % body).encode("utf-8"))
                else:
                    await resp.write(b": ping\n\n")
                await link.wait_for_change(timeout=10.0)
        except (ConnectionResetError, asyncio.CancelledError):
            pass                            # вкладку закрыли — это нормально
        finally:
            await link.release()
        return resp


    async def db_stats(_request: web.Request) -> web.Response:
        return web.json_response(await asyncio.to_thread(dbsrc.stats))

    async def db_wipe(request: web.Request) -> web.Response:
        """
        Необратимая очистка. Подтверждение — на стороне интерфейса (второе
        нажатие), здесь проверяется только то, что агент остановлен.
        """
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "ожидался JSON"}, status=400)

        scope = (payload or {}).get("scope") or ""
        result = await asyncio.to_thread(dbsrc.wipe, scope)
        if result["ok"]:
            return web.json_response(result)
        conflict = result.get("needsStop") or result.get("busy")
        return web.json_response(result, status=409 if conflict else 400)

    async def drives_list(_request: web.Request) -> web.Response:
        return web.json_response(await asyncio.to_thread(drivesrc.list_drives))

    async def drives_update(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "ожидался JSON"}, status=400)
        result = await asyncio.to_thread(drivesrc.update_custom,
                                         payload.get("updates") or {})
        return web.json_response(result, status=200 if result["ok"] else 409)

    app.router.add_get("/api/tick", tick_state)
    app.router.add_get("/api/chat", chat_history)
    app.router.add_post("/api/chat", chat_send)
    app.router.add_get("/api/chat/stream", chat_stream)
    app.router.add_get("/api/db/stats", db_stats)
    app.router.add_post("/api/db/wipe", db_wipe)
    app.router.add_get("/api/drives", drives_list)
    app.router.add_put("/api/drives", drives_update)
    app.router.add_get("/api/logs", logs_tail)
    app.router.add_get("/api/logs/stream", logs_stream)
    app.router.add_get("/api/logs/download", logs_download)
    app.router.add_get("/api/agent/status", agent_status)
    app.router.add_post("/api/agent/start", agent_start)
    app.router.add_post("/api/agent/stop", agent_stop)
    app.router.add_get("/api/config", get_config)
    app.router.add_put("/api/config", put_config)
    app.router.add_post("/api/fs/open", post_open)
    app.router.add_get("/", index)
    app.router.add_static("/", STATIC_DIR, show_index=False)
    return app


def main() -> None:
    # консоль Windows по умолчанию в cp1251 и падает на символах вне неё
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:                                  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="Веб-консоль JAWL")
    parser.add_argument("--host", default="127.0.0.1",
                        help="по умолчанию только localhost; 0.0.0.0 требует токена")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--token", default=os.environ.get("CONSOLE_TOKEN"),
                        help="если не задан, а host не localhost — будет сгенерирован")
    parser.add_argument("--no-browser", action="store_true",
                        help="не открывать браузер при старте")
    parser.add_argument("--keep-agent", action="store_true",
                        help="не останавливать агента при закрытии консоли")
    args = parser.parse_args()

    # На свежей установке рабочих конфигов ещё нет — только образцы
    created = cio.ensure_config_files()
    if created:
        print("Созданы конфиги из образцов: %s" % ", ".join(created))

    token = args.token
    if args.host not in ("127.0.0.1", "localhost", "::1") and not token:
        token = secrets.token_urlsafe(24)
        print("Консоль слушает не только localhost — сгенерирован токен доступа:")
        print("  %s" % token)
        print("  Открывать: http://%s:%d/?token=%s" % (args.host, args.port, token))

    url = "http://%s:%d/" % ("127.0.0.1" if args.host == "0.0.0.0" else args.host, args.port)
    if token:
        url += "?token=%s" % token
    print("JAWL console: %s" % url)

    if not args.no_browser:
        # открываем чуть позже, чтобы сервер успел принять соединение
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    if args.keep_agent:
        print("Агент переживёт закрытие консоли (--keep-agent).")
    else:
        print("Закройте это окно или нажмите Ctrl+C — консоль остановится")
        print("вместе с агентом, если запускали его отсюда.")
    print("")

    line = console_ui.StatusLine()
    line.start()

    def cleanup():
        if not args.keep_agent:
            console_ui.shutdown_owned_agent(line)

    if not args.keep_agent:
        console_ui.install_close_handler(cleanup)

    try:
        web.run_app(make_app(token), host=args.host, port=args.port,
                    print=None, handle_signals=True)
    except KeyboardInterrupt:
        pass
    finally:
        line.stop()
        cleanup()
        print("Консоль остановлена.")
        console_ui.explain_batch_prompt()


if __name__ == "__main__":
    main()
